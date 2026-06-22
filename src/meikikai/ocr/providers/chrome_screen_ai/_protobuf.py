"""Minimal wire-format decoder for Chrome Screen AI VisualAnnotation."""

import struct

DIRECTION_TOP_TO_BOTTOM = 3


class SymbolResult:
    __slots__ = ("text", "confidence", "x", "y", "width", "height", "angle")

    def __init__(self):
        self.text = ""
        self.confidence = 0.0
        self.x = self.y = self.width = self.height = 0
        self.angle = 0.0


class WordResult:
    __slots__ = ("text", "language", "confidence", "x", "y", "width", "height", "angle", "direction", "has_space_after", "symbols")

    def __init__(self):
        self.text = self.language = ""
        self.confidence = 0.0
        self.x = self.y = self.width = self.height = 0
        self.angle = 0.0
        self.direction = 0
        self.has_space_after = False
        self.symbols: list[SymbolResult] = []


class LineResult:
    __slots__ = (
        "text", "language", "block_id", "paragraph_id", "confidence",
        "x", "y", "width", "height", "angle", "direction", "content_type", "words",
    )

    def __init__(self):
        self.text = self.language = ""
        self.block_id = self.paragraph_id = 0
        self.confidence = 0.0
        self.x = self.y = self.width = self.height = 0
        self.angle = 0.0
        self.direction = self.content_type = 0
        self.words: list[WordResult] = []


def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
    raise ValueError("unterminated protobuf varint")


def _decode_raw(data: bytes) -> list[tuple[int, int, object]]:
    pos = 0
    items: list[tuple[int, int, object]] = []
    while pos < len(data):
        try:
            tag, pos = _decode_varint(data, pos)
        except (IndexError, ValueError):
            break

        field_number = tag >> 3
        wire_type = tag & 7
        if wire_type == 0:
            value, pos = _decode_varint(data, pos)
        elif wire_type == 1:
            if pos + 8 > len(data):
                break
            value = struct.unpack("<d", data[pos:pos + 8])[0]
            pos += 8
        elif wire_type == 2:
            try:
                length, pos = _decode_varint(data, pos)
            except (IndexError, ValueError):
                break
            value = data[pos:pos + length]
            pos += length
        elif wire_type == 5:
            if pos + 4 > len(data):
                break
            value = struct.unpack("<f", data[pos:pos + 4])[0]
            pos += 4
        else:
            break
        items.append((field_number, wire_type, value))
    return items


def _parse_rect(data: bytes) -> tuple[int, int, int, int, float]:
    x = y = width = height = 0
    angle = 0.0
    for field_number, wire_type, value in _decode_raw(data):
        if field_number == 1 and wire_type == 0:
            x = value
        elif field_number == 2 and wire_type == 0:
            y = value
        elif field_number == 3 and wire_type == 0:
            width = value
        elif field_number == 4 and wire_type == 0:
            height = value
        elif field_number == 5 and wire_type == 5:
            angle = value
    return x, y, width, height, angle


def _parse_symbol(data: bytes) -> SymbolResult:
    symbol = SymbolResult()
    for field_number, wire_type, value in _decode_raw(data):
        if field_number == 1 and wire_type == 2:
            symbol.x, symbol.y, symbol.width, symbol.height, symbol.angle = _parse_rect(value)
        elif field_number == 2 and wire_type == 2:
            symbol.text = value.decode("utf-8", errors="replace")
        elif field_number == 3 and wire_type == 5:
            symbol.confidence = value
    return symbol


def _parse_word(data: bytes) -> WordResult:
    word = WordResult()
    for field_number, wire_type, value in _decode_raw(data):
        if field_number == 1 and wire_type == 2:
            word.symbols.append(_parse_symbol(value))
        elif field_number == 2 and wire_type == 2:
            word.x, word.y, word.width, word.height, word.angle = _parse_rect(value)
        elif field_number == 3 and wire_type == 2:
            word.text = value.decode("utf-8", errors="replace")
        elif field_number == 5 and wire_type == 2:
            word.language = value.decode("utf-8", errors="replace")
        elif field_number == 6 and wire_type == 0:
            word.has_space_after = bool(value)
        elif field_number == 12 and wire_type == 0:
            word.direction = value
        elif field_number == 15 and wire_type == 5:
            word.confidence = value
    return word


def _parse_line(data: bytes) -> LineResult:
    line = LineResult()
    for field_number, wire_type, value in _decode_raw(data):
        if field_number == 1 and wire_type == 2:
            line.words.append(_parse_word(value))
        elif field_number == 2 and wire_type == 2:
            line.x, line.y, line.width, line.height, line.angle = _parse_rect(value)
        elif field_number == 3 and wire_type == 2:
            line.text = value.decode("utf-8", errors="replace")
        elif field_number == 4 and wire_type == 2:
            line.language = value.decode("utf-8", errors="replace")
        elif field_number == 5 and wire_type == 0:
            line.block_id = value
        elif field_number == 7 and wire_type == 0:
            line.direction = value
        elif field_number == 8 and wire_type == 0:
            line.content_type = value
        elif field_number == 10 and wire_type == 5:
            line.confidence = value
        elif field_number == 11 and wire_type == 0:
            line.paragraph_id = value
    return line


def parse_visual_annotation(data: bytes) -> list[LineResult]:
    return [
        _parse_line(value)
        for field_number, wire_type, value in _decode_raw(data)
        if field_number == 2 and wire_type == 2
    ]
