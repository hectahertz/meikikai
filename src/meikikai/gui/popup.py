# meikikai/gui/popup.py
import logging
import os
import threading
from ctypes import c_void_p
from html import escape
from typing import List, Optional

from PyQt6.QtCore import QTimer, QPoint, QRect, QSize
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from meikikai.config.config import config
from meikikai.dictionary.customdict import DEFAULT_FREQ
from meikikai.dictionary.lookup import DictionaryEntry, KanjiEntry, LookupResult
from meikikai.gui.input import pause_macos_media_if_playing, play_macos_media
from meikikai.utils.capture_state import is_capture_interaction_active

try:
    import objc
    from AppKit import (
        NSApplicationActivateIgnoringOtherApps,
        NSMainMenuWindowLevel,
        NSWorkspace,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowCollectionBehaviorIgnoresCycle,
        NSWindowCollectionBehaviorTransient,
    )
except ImportError:
    objc = None
    NSApplicationActivateIgnoringOtherApps = None
    NSMainMenuWindowLevel = None
    NSWorkspace = None
    NSWindowCollectionBehaviorCanJoinAllSpaces = None
    NSWindowCollectionBehaviorFullScreenAuxiliary = None
    NSWindowCollectionBehaviorIgnoresCycle = None
    NSWindowCollectionBehaviorTransient = None

logger = logging.getLogger(__name__)

FONT_FAMILY = "Hiragino Sans"
FONT_STACK_QSS = '"SF Pro Text", "Helvetica Neue", "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif'

POPUP_WIDTH = 496
CONTENT_MARGIN_LEFT = 12
CONTENT_MARGIN_TOP = 10
CONTENT_MARGIN_RIGHT = 12
CONTENT_MARGIN_BOTTOM = 14
CONTENT_WIDTH = POPUP_WIDTH - CONTENT_MARGIN_LEFT - CONTENT_MARGIN_RIGHT - 2
SHADOW_MARGIN = 0

POPUP_BG = "rgba(24, 27, 36, 246)"
POPUP_BORDER = "rgba(237, 241, 247, 34)"
TEXT_COLOR = "#edf1f7"
DEFINITION_COLOR = "#eef2f8"
MUTED_COLOR = "#a8b0c2"
WORD_COLOR = "#8bd8ff"
READING_COLOR = "#98e6a3"
SEPARATOR_COLOR = "rgba(237, 241, 247, 22)"
META_COLOR = "#929cae"
META_LABEL_COLOR = "#768195"
DECONJ_COLOR = "#c6b57f"
SENSE_NUMBER_COLOR = "#768195"
KANJI_CARD_BG = "rgba(139, 216, 255, 12)"
KANJI_CARD_BORDER = "rgba(139, 216, 255, 32)"
KANJI_GLYPH_BG = "rgba(139, 216, 255, 18)"

WORD_FONT_SIZE = 21
KANJI_GLYPH_FONT_SIZE = 31
READING_FONT_SIZE = 14
DEFINITION_FONT_SIZE = 12
META_FONT_SIZE = 11
DETAIL_FONT_SIZE = 10

MAX_VOCAB_ENTRIES = 3
MAX_SENSES_PER_ENTRY = 3
MAX_GLOSSES_PER_SENSE = 4


class FlowLayout(QLayout):
    def __init__(self, parent=None, h_spacing=7, v_spacing=5):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())

        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        h_spacing = self._h_spacing
        v_spacing = self._v_spacing

        for item in self._items:
            item_size = item.sizeHint()
            item_width = min(item_size.width(), rect.width())
            item_height = item.heightForWidth(item_width) if item.hasHeightForWidth() else item_size.height()

            next_x = x + item_width + h_spacing
            if next_x - h_spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + v_spacing
                next_x = x + item_width + h_spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), QSize(item_width, item_height)))

            x = next_x
            line_height = max(line_height, item_height)

        return y + line_height - rect.y()


class Popup(QWidget):
    def __init__(self, shared_state):
        super().__init__()
        self._latest_data = None
        self._last_latest_data = None
        self._data_lock = threading.Lock()
        self._previous_active_app_on_mac = None
        self._auto_pause_media_triggered = False
        self._auto_pause_media_resume_deferred = False

        self.shared_state = shared_state

        self.is_visible = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.process_latest_data_loop)
        self.timer.start(10)

        base_font = QFont(FONT_FAMILY)
        base_font.setPixelSize(DEFINITION_FONT_SIZE)
        self.setFont(base_font)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        mac_always_show_tool_window = getattr(Qt.WidgetAttribute, "WA_MacAlwaysShowToolWindow", None)
        if mac_always_show_tool_window is not None:
            self.setAttribute(mac_always_show_tool_window)
        self.setStyleSheet("background: transparent;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        main_layout.setSpacing(0)

        self.frame = QFrame()
        self.frame.setFrameShape(QFrame.Shape.NoFrame)
        self.frame.setObjectName("popupFrame")
        self.frame.setFixedWidth(POPUP_WIDTH)
        self._apply_frame_stylesheet()
        main_layout.addWidget(self.frame)

        self.content_layout = QVBoxLayout(self.frame)
        self.content_layout.setContentsMargins(
            CONTENT_MARGIN_LEFT,
            CONTENT_MARGIN_TOP,
            CONTENT_MARGIN_RIGHT,
            CONTENT_MARGIN_BOTTOM,
        )
        self.content_layout.setSpacing(0)
        self.content_widget = None

        self.hide()
        self._configure_macos_window()

    def _apply_frame_stylesheet(self):
        self.frame.setStyleSheet(f"""
            QFrame#popupFrame {{
                background-color: {POPUP_BG};
                color: {TEXT_COLOR};
                border-radius: 16px;
                border: 1px solid {POPUP_BORDER};
            }}
        """)

    def set_latest_data(self, data):
        with self._data_lock:
            self._latest_data = data

    def get_latest_data(self):
        with self._data_lock:
            return self._latest_data

    def get_latest_export_data(self):
        with self._data_lock:
            data = self._last_latest_data
        if not self.is_visible or config.is_paused:
            return None
        if not self._top_visible_dictionary_entry(data):
            return None
        return data

    @staticmethod
    def _entries_from_data(data):
        if isinstance(data, LookupResult):
            return data.entries
        return data

    @classmethod
    def _top_visible_dictionary_entry(cls, data) -> Optional[DictionaryEntry]:
        entries = cls._entries_from_data(data)
        if not entries:
            return None
        for entry in entries:
            if isinstance(entry, DictionaryEntry):
                return entry
        return None

    def process_latest_data_loop(self):
        if is_capture_interaction_active():
            self.hide_popup()
            return

        latest_data = self.get_latest_data()
        if latest_data and latest_data != self._last_latest_data:
            self._set_entries(latest_data)
        with self._data_lock:
            self._last_latest_data = latest_data

        mouse_pos = QCursor.pos()
        self.move_to(mouse_pos.x(), mouse_pos.y())

        if latest_data and not config.is_paused:
            self.show_popup()
        else:
            self.hide_popup()

    def _set_entries(self, data: Optional[LookupResult | List[DictionaryEntry | KanjiEntry]]):
        entries = self._entries_from_data(data)
        content = QWidget()
        content.setFixedWidth(CONTENT_WIDTH)
        content.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        content.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        shown_vocab_count = 0
        hidden_vocab_count = 0
        hidden_sense_count = 0
        hidden_gloss_count = 0
        previous_was_vocab = False
        if entries:
            for entry in entries:
                if isinstance(entry, KanjiEntry):
                    if layout.count() > 0:
                        layout.addSpacing(8)
                    layout.addWidget(self._kanji_card(entry))
                    previous_was_vocab = False
                    continue

                if shown_vocab_count >= MAX_VOCAB_ENTRIES:
                    hidden_vocab_count += 1
                    continue

                if previous_was_vocab:
                    layout.addWidget(self._separator())
                entry_widget, omitted_senses, omitted_glosses = self._dictionary_entry(entry)
                layout.addWidget(entry_widget)
                hidden_sense_count += omitted_senses
                hidden_gloss_count += omitted_glosses
                shown_vocab_count += 1
                previous_was_vocab = True

        footer = self._omission_footer(hidden_vocab_count, hidden_sense_count, hidden_gloss_count)
        if footer:
            if layout.count() > 0:
                layout.addSpacing(7)
            layout.addWidget(footer)

        self._finalize_fixed_height(content)
        self._replace_content_widget(content)

    def _replace_content_widget(self, content: QWidget):
        old_content = self.content_widget
        if old_content is not None:
            self.content_layout.removeWidget(old_content)
            old_content.hide()
            old_content.deleteLater()

        self.content_widget = content
        self.content_layout.addWidget(content)
        self._resize_to_content()

    def _resize_to_content(self):
        self.content_layout.invalidate()
        self.content_layout.activate()

        margins = self.content_layout.contentsMargins()
        content_height = self.content_widget.height() if self.content_widget else 0
        height = margins.top() + content_height + margins.bottom() + 2
        self.frame.setFixedSize(POPUP_WIDTH, height)
        self.setFixedSize(POPUP_WIDTH + SHADOW_MARGIN * 2, height + SHADOW_MARGIN * 2)

    def _finalize_fixed_height(self, widget: QWidget):
        layout = widget.layout()
        if layout:
            layout.invalidate()
            layout.activate()
        widget.setFixedHeight(widget.sizeHint().height())

    @staticmethod
    def _escape(value) -> str:
        return escape(str(value), quote=False)

    @staticmethod
    def _contains_html(value: str) -> bool:
        return "<" in value and ">" in value

    def _gloss_to_html(self, gloss) -> str:
        text = str(gloss).strip()
        if self._contains_html(text):
            return text
        return self._escape(text)

    def _join_escaped(self, values, separator=", ") -> str:
        return separator.join(self._escape(value) for value in values if value)

    def _font(self, size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        font = QFont(FONT_FAMILY)
        font.setPixelSize(size)
        font.setWeight(weight)
        return font

    def _plain_label(
        self,
        text: str,
        color: str,
        size: int,
        weight: QFont.Weight = QFont.Weight.Normal,
        max_width: int = CONTENT_WIDTH,
    ) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setFont(self._font(size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent; border: none; font-family: {FONT_STACK_QSS};")
        if label.sizeHint().width() > max_width:
            label.setWordWrap(True)
            label.setFixedWidth(max_width)
        else:
            label.setWordWrap(False)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return label

    def _rich_label(self, html: str, color: str, size: int, width: int) -> QLabel:
        label = QLabel(html)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setFont(self._font(size))
        label.setFixedWidth(width)
        label.setStyleSheet(
            f"color: {color}; background: transparent; border: none; "
            f"font-family: {FONT_STACK_QSS}; font-size: {size}px;"
        )
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        return label

    def _metadata_label(self, html: str, width: int = CONTENT_WIDTH, color: str = META_COLOR) -> QLabel:
        return self._rich_label(
            f'<span style="color:{color}; font-size:{META_FONT_SIZE}px; line-height:125%;">{html}</span>',
            color,
            META_FONT_SIZE,
            width,
        )

    def _flow_container(
        self,
        width: int = CONTENT_WIDTH,
        h_spacing: int = 7,
        v_spacing: int = 5,
    ) -> tuple[QWidget, FlowLayout]:
        container = QWidget()
        container.setFixedWidth(width)
        container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        container.setStyleSheet("background: transparent; border: none;")
        layout = FlowLayout(container, h_spacing=h_spacing, v_spacing=v_spacing)
        return container, layout

    def _finalize_flow_container(self, container: QWidget, layout: FlowLayout, width: int):
        layout.invalidate()
        height = layout.heightForWidth(width)
        container.setFixedSize(width, height)

    @staticmethod
    def _unique_sense_values(senses: list, key: str) -> list[str]:
        values = []
        seen = set()
        for sense in senses:
            for value in sense.get(key, []):
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
        return values

    def _entry_metadata(self, entry: DictionaryEntry) -> tuple[list[str], str]:
        metadata = []
        shown_senses = []
        for sense in entry.senses:
            if sense.get('glosses'):
                shown_senses.append(sense)
            if len(shown_senses) >= MAX_SENSES_PER_ENTRY:
                break

        pos_values = self._unique_sense_values(shown_senses, 'pos')
        tag_values = self._unique_sense_values(shown_senses, 'tags')
        if pos_values:
            metadata.append(" · ".join(pos_values))
        metadata.extend(tag_values)

        if entry.freq < DEFAULT_FREQ:
            metadata.append(f"#{entry.freq}")

        deconj = ""
        if entry.deconjugation_process:
            steps = [p for p in entry.deconjugation_process if p]
            if steps and steps[0] == entry.written_form:
                steps = steps[1:]
            deconj = " · ".join(steps)

        return metadata, deconj

    def _metadata_html(self, values: list[str]) -> str:
        return f' <span style="color:{META_LABEL_COLOR};">·</span> '.join(
            self._escape(value) for value in values if value
        )

    def _deconjugation_html(self, value: str) -> str:
        return (
            f'<span style="color:{META_LABEL_COLOR}; font-weight:700;">inflected</span>'
            f' <span style="color:{META_LABEL_COLOR};">·</span> {self._escape(value)}'
        )

    @staticmethod
    def _plural(count: int, singular: str, plural: str) -> str:
        unit = singular if count == 1 else plural
        return f"{count} {unit}"

    def _omission_footer(
        self,
        hidden_vocab_count: int,
        hidden_sense_count: int,
        hidden_gloss_count: int,
    ) -> QLabel | None:
        parts = []
        if hidden_vocab_count:
            parts.append(self._plural(hidden_vocab_count, "more entry", "more entries"))
        if hidden_sense_count:
            parts.append(self._plural(hidden_sense_count, "more sense", "more senses"))
        if hidden_gloss_count:
            parts.append(self._plural(hidden_gloss_count, "more gloss", "more glosses"))
        if not parts:
            return None
        return self._metadata_label(f'+ {" · ".join(parts)}')

    def _entry_definition_html(self, entry: DictionaryEntry) -> tuple[str, int, int]:
        sense_parts = []
        hidden_gloss_count = 0
        for sense in entry.senses:
            glosses = [self._gloss_to_html(gloss) for gloss in sense.get('glosses', []) if gloss]
            if not glosses:
                continue

            shown_glosses = glosses[:MAX_GLOSSES_PER_SENSE]
            hidden_gloss_count += max(0, len(glosses) - MAX_GLOSSES_PER_SENSE)
            sense_parts.append(", ".join(shown_glosses))

        hidden_sense_count = max(0, len(sense_parts) - MAX_SENSES_PER_ENTRY)
        sense_parts = sense_parts[:MAX_SENSES_PER_ENTRY]

        if len(sense_parts) <= 1:
            return (sense_parts[0] if sense_parts else ""), hidden_sense_count, hidden_gloss_count

        rows = []
        for index, sense_text in enumerate(sense_parts, 1):
            rows.append(
                f'<span style="color:{SENSE_NUMBER_COLOR}; font-weight:800;">{index}</span>'
                f'&nbsp;{sense_text}'
            )
        return "<br>".join(rows), hidden_sense_count, hidden_gloss_count

    def _dictionary_entry(self, entry: DictionaryEntry) -> tuple[QWidget, int, int]:
        entry_widget = QWidget()
        entry_widget.setFixedWidth(CONTENT_WIDTH)
        entry_widget.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(entry_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        row, row_layout = self._flow_container(h_spacing=8, v_spacing=2)
        row_layout.addWidget(self._plain_label(
            entry.written_form,
            WORD_COLOR,
            WORD_FONT_SIZE,
            QFont.Weight.Medium,
        ))
        if entry.reading:
            row_layout.addWidget(self._plain_label(
                f"[{entry.reading}]",
                READING_COLOR,
                READING_FONT_SIZE,
                QFont.Weight.DemiBold,
            ))
        self._finalize_flow_container(row, row_layout, CONTENT_WIDTH)
        layout.addWidget(row)

        metadata, deconj = self._entry_metadata(entry)
        if metadata:
            layout.addSpacing(1)
            layout.addWidget(self._metadata_label(self._metadata_html(metadata)))
        if deconj:
            layout.addSpacing(2)
            layout.addWidget(self._metadata_label(self._deconjugation_html(deconj), color=DECONJ_COLOR))

        definition_html, hidden_sense_count, hidden_gloss_count = self._entry_definition_html(entry)
        if definition_html:
            layout.addSpacing(5 if metadata or deconj else 3)
            layout.addWidget(self._rich_label(definition_html, DEFINITION_COLOR, DEFINITION_FONT_SIZE, CONTENT_WIDTH))

        self._finalize_fixed_height(entry_widget)
        return entry_widget, hidden_sense_count, hidden_gloss_count

    def _separator(self) -> QWidget:
        container = QWidget()
        container.setFixedWidth(CONTENT_WIDTH)
        container.setFixedHeight(13)
        container.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(0)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {SEPARATOR_COLOR}; border: none;")
        layout.addWidget(line)
        return container

    def _kanji_card(self, entry: KanjiEntry) -> QFrame:
        card = QFrame()
        card.setObjectName("kanjiCard")
        card.setFixedWidth(CONTENT_WIDTH)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        card.setStyleSheet(f"""
            QFrame#kanjiCard {{
                background-color: {KANJI_CARD_BG};
                border: 1px solid {KANJI_CARD_BORDER};
                border-radius: 10px;
            }}
        """)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(9)

        glyph = QFrame()
        glyph.setFixedSize(48, 52)
        glyph.setStyleSheet(f"background-color: {KANJI_GLYPH_BG}; border: none; border-radius: 9px;")
        glyph_layout = QVBoxLayout(glyph)
        glyph_layout.setContentsMargins(0, 0, 0, 1)
        glyph_layout.setSpacing(0)
        glyph_label = self._plain_label(
            entry.character,
            WORD_COLOR,
            KANJI_GLYPH_FONT_SIZE,
            QFont.Weight.Medium,
            48,
        )
        glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph_layout.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)

        right_width = CONTENT_WIDTH - 16 - 48 - 9
        details = QWidget()
        details.setFixedWidth(right_width)
        details.setStyleSheet("background: transparent; border: none;")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(2)

        readings = self._join_escaped(entry.readings)
        if readings:
            details_layout.addWidget(self._rich_label(
                f'<span style="color:{READING_COLOR}; font-weight:700;">[{readings}]</span>',
                READING_COLOR,
                READING_FONT_SIZE,
                right_width,
            ))

        meanings = self._join_escaped(entry.meanings)
        if meanings:
            details_layout.addWidget(self._rich_label(meanings, DEFINITION_COLOR, DEFINITION_FONT_SIZE, right_width))

        examples_html = self._kanji_examples_html(entry)
        if examples_html:
            details_layout.addWidget(self._rich_label(examples_html, MUTED_COLOR, DETAIL_FONT_SIZE, right_width))

        components_html = self._kanji_components_html(entry)
        if components_html:
            details_layout.addWidget(self._rich_label(components_html, MUTED_COLOR, DETAIL_FONT_SIZE, right_width))

        layout.addWidget(details, 1)
        self._finalize_fixed_height(card)
        return card

    def _kanji_examples_html(self, entry: KanjiEntry) -> str:
        parts = []
        for ex in entry.examples:
            word = self._escape(ex.get('w', ''))
            reading = self._escape(ex.get('r', ''))
            meaning = self._escape(ex.get('m', ''))
            if word or reading or meaning:
                parts.append(
                    f'<span style="color:{WORD_COLOR}; font-weight:700;">{word}</span> '
                    f'<span style="color:{READING_COLOR};">[{reading}]</span> {meaning}'
                )
        if not parts:
            return ""
        return f'<span style="color:{META_LABEL_COLOR}; font-weight:700;">ex</span> {"; ".join(parts)}'

    def _kanji_components_html(self, entry: KanjiEntry) -> str:
        parts = []
        for component in entry.components:
            char = self._escape(component.get('c', ''))
            meaning = self._escape(component.get('m', ''))
            if meaning:
                parts.append(f'<span style="color:{WORD_COLOR};">{char}</span> {meaning}')
            elif char:
                parts.append(f'<span style="color:{WORD_COLOR};">{char}</span>')
        if not parts:
            return ""
        return f'<span style="color:{META_LABEL_COLOR}; font-weight:700;">parts</span> {" · ".join(parts)}'

    def move_to(self, x, y):
        cursor_point = QPoint(x, y)
        screen = QApplication.screenAt(cursor_point) or QApplication.primaryScreen()
        screen_geo = screen.geometry()
        popup_size = self.size()
        offset = 15

        mode = config.popup_position_mode

        if mode == 'visual_novel_mode':
            screen_height = screen_geo.height()
            cursor_y_in_screen = y - screen_geo.top()
            is_below = True
            if cursor_y_in_screen > (2 * screen_height / 3):
                is_below = False
            elif cursor_y_in_screen < (screen_height / 3):
                is_below = True
            else:
                is_below = cursor_y_in_screen < (screen_height / 2)
            final_y = (y + offset) if is_below else (y - popup_size.height() - offset)

            if final_y < screen_geo.top():
                final_y = screen_geo.top()
            if final_y + popup_size.height() > screen_geo.bottom():
                final_y = screen_geo.bottom() - popup_size.height()

            screen_width = screen_geo.width()
            cursor_x_in_screen = x - screen_geo.left()
            pos_right = x + offset
            pos_center = x - popup_size.width() / 2.0
            pos_left = x - popup_size.width() - offset

            if cursor_x_in_screen < screen_width / 2.0:
                ratio = cursor_x_in_screen / (screen_width / 2.0)
                final_x = pos_right * (1 - ratio) + pos_center * ratio
            else:
                ratio = (cursor_x_in_screen - (screen_width / 2.0)) / (screen_width / 2.0)
                final_x = pos_center * (1 - ratio) + pos_left * ratio

        elif mode == 'flip_horizontally':
            preferred_x = x + offset
            final_x = preferred_x if preferred_x + popup_size.width() <= screen_geo.right() else x - popup_size.width() - offset

            final_y = y + offset
            if final_y + popup_size.height() > screen_geo.bottom():
                final_y = screen_geo.bottom() - popup_size.height()
            if final_y < screen_geo.top():
                final_y = screen_geo.top()

        elif mode == 'flip_vertically':
            final_x = x + offset
            if final_x + popup_size.width() > screen_geo.right():
                final_x = screen_geo.right() - popup_size.width()
            if final_x < screen_geo.left():
                final_x = screen_geo.left()

            preferred_y = y + offset
            final_y = preferred_y if preferred_y + popup_size.height() <= screen_geo.bottom() else y - popup_size.height() - offset

        else:
            preferred_x = x + offset
            final_x = preferred_x if preferred_x + popup_size.width() <= screen_geo.right() else x - popup_size.width() - offset

            preferred_y = y + offset
            final_y = preferred_y if preferred_y + popup_size.height() <= screen_geo.bottom() else y - popup_size.height() - offset

        final_x = max(screen_geo.left(), min(final_x, screen_geo.right() - popup_size.width()))
        final_y = max(screen_geo.top(), min(final_y, screen_geo.bottom() - popup_size.height()))

        self.move(int(final_x), int(final_y))

    def hide_popup(self):
        if not self.is_visible:
            return
        self.hide()

    def hideEvent(self, event):
        was_visible = self.is_visible
        super().hideEvent(event)
        if not was_visible:
            return

        self.is_visible = False
        self._resume_auto_paused_media()
        QTimer.singleShot(50, lambda: self._release_lock_safely())
        QTimer.singleShot(0, self._restore_focus_on_mac)

    def _release_lock_safely(self):
        logger.debug("hide_popup releasing lock...")
        self.shared_state.screen_lock.release()
        logger.debug("...successfully released lock by hide_popup")

    def show_popup(self):
        if self.is_visible:
            return

        self._store_active_app_on_mac()
        self._configure_macos_window()

        logger.debug("show_popup acquiring lock...")
        self.shared_state.screen_lock.acquire()
        logger.debug("...successfully acquired lock by show_popup")

        self._pause_media_for_popup()
        self.is_visible = True
        self.show()
        self.raise_()
        self._configure_macos_window()
        self._order_macos_window_front()

    def _pause_media_for_popup(self):
        if self._auto_pause_media_triggered:
            return
        if not config.auto_pause_media:
            return

        if pause_macos_media_if_playing():
            self._auto_pause_media_triggered = True

    def _resume_auto_paused_media(self):
        if not self._auto_pause_media_triggered:
            self._auto_pause_media_resume_deferred = False
            return
        if is_capture_interaction_active():
            self._schedule_deferred_auto_resume()
            return
        if self.is_visible:
            self._auto_pause_media_resume_deferred = False
            return

        try:
            play_macos_media()
        finally:
            self._auto_pause_media_triggered = False
            self._auto_pause_media_resume_deferred = False

    def _schedule_deferred_auto_resume(self):
        if self._auto_pause_media_resume_deferred:
            return
        self._auto_pause_media_resume_deferred = True
        QTimer.singleShot(100, self._deferred_auto_resume_tick)

    def _deferred_auto_resume_tick(self):
        self._auto_pause_media_resume_deferred = False
        self._resume_auto_paused_media()

    def _macos_window(self):
        if not objc:
            return None

        ns_view = objc.objc_object(c_void_p=c_void_p(int(self.winId())))
        return ns_view.window()

    def _configure_macos_window(self):
        try:
            ns_window = self._macos_window()
            if not ns_window:
                return

            collection_behavior = (
                NSWindowCollectionBehaviorCanJoinAllSpaces |
                NSWindowCollectionBehaviorFullScreenAuxiliary |
                NSWindowCollectionBehaviorTransient |
                NSWindowCollectionBehaviorIgnoresCycle
            )
            ns_window.setCollectionBehavior_(collection_behavior)
            ns_window.setLevel_(NSMainMenuWindowLevel)
            ns_window.setCanHide_(False)
            ns_window.setHidesOnDeactivate_(False)
        except Exception as e:
            logger.warning(f"Failed to configure macOS popup window: {e}")

    def _order_macos_window_front(self):
        try:
            ns_window = self._macos_window()
            if ns_window:
                ns_window.orderFrontRegardless()
        except Exception as e:
            logger.warning(f"Failed to order macOS window front: {e}")

    def _store_active_app_on_mac(self):
        if not NSWorkspace:
            return

        try:
            active_app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if active_app and active_app.processIdentifier() != os.getpid():
                self._previous_active_app_on_mac = active_app
            else:
                self._previous_active_app_on_mac = None
        except Exception as e:
            logger.warning(f"Failed to store active app: {e}")
            self._previous_active_app_on_mac = None

    def _restore_focus_on_mac(self):
        if not NSApplicationActivateIgnoringOtherApps or not self._previous_active_app_on_mac:
            return

        try:
            self._previous_active_app_on_mac.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        except Exception as e:
            logger.warning(f"Failed to restore focus: {e}")
        finally:
            self._previous_active_app_on_mac = None

    def reapply_settings(self):
        logger.debug("Popup: Re-applying fixed popup styling.")
        self._apply_frame_stylesheet()
        self._resize_to_content()
