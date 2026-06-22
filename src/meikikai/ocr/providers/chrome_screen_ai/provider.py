import logging
import re
from typing import List, Optional

from PIL import Image

from meikikai.ocr.interface import BoundingBox, OcrProvider, Paragraph, Word
from meikikai.ocr.providers.chrome_screen_ai._protobuf import DIRECTION_TOP_TO_BOTTOM, LineResult, SymbolResult, WordResult
from meikikai.ocr.providers.chrome_screen_ai._screen_ai import ChromeScreenAiEngine
from meikikai.ocr.providers.postprocessing import group_lines_into_paragraphs

logger = logging.getLogger(__name__)

JAPANESE_REGEX = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')


class ChromeScreenAiProvider(OcrProvider):
    """OCR provider backed by Chrome's local Screen AI component."""

    NAME = "Chrome Screen AI"

    def __init__(self):
        logger.info(f"initializing {self.NAME} provider...")
        try:
            self.engine = ChromeScreenAiEngine()
        except FileNotFoundError as e:
            logger.warning("%s is not installed: %s", self.NAME, e)
            raise RuntimeError(str(e)) from e
        except Exception as e:
            logger.error("failed to initialize %s: %s", self.NAME, e, exc_info=True)
            raise RuntimeError(str(e)) from e
        logger.info(f"{self.NAME} initialized successfully.")

    def scan(self, image: Image.Image) -> Optional[List[Paragraph]]:
        if image.width == 0 or image.height == 0:
            logger.error("invalid image dimensions received.")
            return None

        try:
            lines, image_size = self.engine.scan(image)
            return self._to_meikikai_paragraphs(lines, *image_size)
        except Exception as e:
            logger.error(f"an error occurred in {self.NAME}: {e}", exc_info=True)
            return None

    def _to_meikikai_paragraphs(self, line_results: list[LineResult], img_width: int, img_height: int) -> List[Paragraph]:
        lines: List[Paragraph] = []
        for line_result in line_results:
            full_text = self._line_text(line_result)
            if not full_text or not JAPANESE_REGEX.search(full_text):
                continue

            line_box = self._to_normalized_bbox(line_result.x, line_result.y, line_result.width, line_result.height, img_width, img_height)
            if line_box.width <= 0 or line_box.height <= 0:
                line_box = self._box_from_words(line_result.words, img_width, img_height)
            if line_box.width <= 0 or line_box.height <= 0:
                continue

            is_vertical = line_result.direction == DIRECTION_TOP_TO_BOTTOM or line_box.width * 1.5 < line_box.height
            words = self._line_words(line_result, line_box, full_text, img_width, img_height, is_vertical)
            if not words:
                words = [Word(text=full_text, separator="", box=line_box)]

            lines.append(Paragraph(
                full_text=full_text,
                words=words,
                box=line_box,
                is_vertical=is_vertical,
            ))

        return group_lines_into_paragraphs(lines)

    def _line_text(self, line_result: LineResult) -> str:
        text = (line_result.text or "").strip()
        if text:
            return text

        parts = []
        for word in line_result.words:
            word_text = word.text or "".join(symbol.text for symbol in word.symbols)
            if not word_text:
                continue
            parts.append(word_text)
            if word.has_space_after:
                parts.append(" ")
        return "".join(parts).strip()

    def _line_words(
            self,
            line_result: LineResult,
            line_box: BoundingBox,
            full_text: str,
            img_width: int,
            img_height: int,
            is_vertical: bool,
    ) -> List[Word]:
        words: List[Word] = []
        for word_result in line_result.words:
            symbol_words = self._symbol_words(word_result, img_width, img_height)
            if symbol_words:
                if word_result.has_space_after:
                    last_word = symbol_words[-1]
                    symbol_words[-1] = Word(text=last_word.text, separator=" ", box=last_word.box)
                words.extend(symbol_words)
                continue

            text = (word_result.text or "").strip()
            if not text:
                continue
            box = self._word_box(word_result, img_width, img_height)
            if box.width <= 0 or box.height <= 0:
                continue
            separator = " " if word_result.has_space_after else ""
            words.append(Word(text=text, separator=separator, box=box))

        if words:
            return words

        return self._estimated_character_words(line_box, full_text, is_vertical)

    def _symbol_words(self, word_result: WordResult, img_width: int, img_height: int) -> List[Word]:
        symbols = [symbol for symbol in word_result.symbols if (symbol.text or "").strip()]
        if not symbols:
            return []

        words: List[Word] = []
        for symbol in symbols:
            box = self._symbol_box(symbol, img_width, img_height)
            if box.width <= 0 or box.height <= 0:
                return []
            words.append(Word(text=symbol.text.strip(), separator="", box=box))
        return words

    def _word_box(self, word_result: WordResult, img_width: int, img_height: int) -> BoundingBox:
        return self._to_normalized_bbox(word_result.x, word_result.y, word_result.width, word_result.height, img_width, img_height)

    def _symbol_box(self, symbol_result: SymbolResult, img_width: int, img_height: int) -> BoundingBox:
        return self._to_normalized_bbox(symbol_result.x, symbol_result.y, symbol_result.width, symbol_result.height, img_width, img_height)

    def _box_from_words(self, words: list[WordResult], img_width: int, img_height: int) -> BoundingBox:
        word_boxes: List[BoundingBox] = []
        for word in words:
            box = self._word_box(word, img_width, img_height)
            if box.width > 0 and box.height > 0:
                word_boxes.append(box)
                continue
            word_boxes.extend(
                symbol_box for symbol_box in (self._symbol_box(symbol, img_width, img_height) for symbol in word.symbols)
                if symbol_box.width > 0 and symbol_box.height > 0
            )
        if not word_boxes:
            return BoundingBox(0, 0, 0, 0)

        min_x = min(box.center_x - box.width / 2 for box in word_boxes)
        max_x = max(box.center_x + box.width / 2 for box in word_boxes)
        min_y = min(box.center_y - box.height / 2 for box in word_boxes)
        max_y = max(box.center_y + box.height / 2 for box in word_boxes)
        width = max_x - min_x
        height = max_y - min_y
        return BoundingBox(min_x + width / 2, min_y + height / 2, width, height)

    def _to_normalized_bbox(self, x: int, y: int, width: int, height: int, img_width: int, img_height: int) -> BoundingBox:
        if img_width <= 0 or img_height <= 0:
            return BoundingBox(0, 0, 0, 0)

        x = max(0, min(float(x), float(img_width)))
        y = max(0, min(float(y), float(img_height)))
        width = max(0, min(float(width), float(img_width) - x))
        height = max(0, min(float(height), float(img_height) - y))
        return BoundingBox(
            center_x=(x + width / 2) / img_width,
            center_y=(y + height / 2) / img_height,
            width=width / img_width,
            height=height / img_height,
        )

    def _estimated_character_words(self, line_box: BoundingBox, full_text: str, is_vertical: bool) -> List[Word]:
        characters = [character for character in full_text if not character.isspace()]
        if not characters:
            return []

        if is_vertical:
            char_height = line_box.height / len(characters)
            top = line_box.center_y - line_box.height / 2
            return [
                Word(
                    text=character,
                    separator="",
                    box=BoundingBox(
                        center_x=line_box.center_x,
                        center_y=top + char_height * (index + 0.5),
                        width=line_box.width,
                        height=char_height,
                    ),
                )
                for index, character in enumerate(characters)
            ]

        char_width = line_box.width / len(characters)
        left = line_box.center_x - line_box.width / 2
        return [
            Word(
                text=character,
                separator="",
                box=BoundingBox(
                    center_x=left + char_width * (index + 0.5),
                    center_y=line_box.center_y,
                    width=char_width,
                    height=line_box.height,
                ),
            )
            for index, character in enumerate(characters)
        ]
