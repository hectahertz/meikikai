# meikikai/gui/popup.py
import logging
import math
import os
import threading
from ctypes import c_void_p
from html import escape
from typing import List, Optional

from PyQt6.QtCore import QTimer, QPoint, QRect, QSize
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QFont, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from meikikai.config.config import config
from meikikai.dictionary.customdict import DEFAULT_FREQ
from meikikai.dictionary.lookup import DictionaryEntry, KanjiEntry, KANJI_REGEX, LookupResult
from meikikai.gui.input import pause_macos_media_if_playing, play_macos_media
from meikikai.gui.popup_design.styles import (
    kanji_card_stylesheet,
    kanji_glyph_stylesheet,
    plain_label_stylesheet,
    popup_frame_stylesheet,
    rich_label_stylesheet,
    separator_stylesheet,
    transparent_stylesheet,
)
from meikikai.gui.popup_design.tokens import popup_tokens
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

    @staticmethod
    def _item_baseline(item) -> int:
        widget = item.widget()
        if not widget:
            return 0
        margins = widget.contentsMargins()
        return margins.top() + widget.fontMetrics().ascent()

    @staticmethod
    def _line_height(line_items: list[tuple[object, int, int, int, int]]) -> int:
        if not line_items:
            return 0
        baseline = max(item_baseline for _, _, _, _, item_baseline in line_items)
        return max(baseline + item_height - item_baseline for _, _, _, item_height, item_baseline in line_items)

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_items = []
        h_spacing = self._h_spacing
        v_spacing = self._v_spacing

        def flush_line():
            nonlocal y
            line_height = self._line_height(line_items)
            if not test_only and line_items:
                line_baseline = max(item_baseline for _, _, _, _, item_baseline in line_items)
                for item, item_x, item_width, item_height, item_baseline in line_items:
                    item_y = y + max(0, line_baseline - item_baseline)
                    item.setGeometry(QRect(QPoint(item_x, item_y), QSize(item_width, item_height)))
            y += line_height
            return line_height

        for item in self._items:
            item_size = item.sizeHint()
            item_width = min(item_size.width(), rect.width())
            item_height = item.heightForWidth(item_width) if item.hasHeightForWidth() else item_size.height()

            next_x = x + item_width + h_spacing
            if next_x - h_spacing > rect.right() and line_items:
                flush_line()
                y += v_spacing
                x = rect.x()
                next_x = x + item_width + h_spacing
                line_items = []

            line_items.append((item, x, item_width, item_height, self._item_baseline(item)))
            x = next_x

        flush_line()
        return y - rect.y()


class Popup(QWidget):
    def __init__(self, shared_state):
        super().__init__()
        self._latest_data = None
        self._last_latest_data = None
        self._data_lock = threading.Lock()
        self._previous_active_app_on_mac = None
        self._auto_pause_media_triggered = False
        self._auto_pause_media_resume_deferred = False
        self._suppress_next_focus_restore = False
        self._tokens = self._current_tokens()
        self._layout_tier = self._current_layout_tier()

        self.shared_state = shared_state

        self.is_visible = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.process_latest_data_loop)
        self.timer.start(10)

        base_font = QFont(self._tokens.font_family)
        base_font.setPixelSize(self._tokens.definition_font_size)
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
        self.setStyleSheet(transparent_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self._tokens.shadow_margin,
            self._tokens.shadow_margin,
            self._tokens.shadow_margin,
            self._tokens.shadow_margin,
        )
        main_layout.setSpacing(0)

        self.frame = QFrame()
        self.frame.setFrameShape(QFrame.Shape.NoFrame)
        self.frame.setObjectName("popupFrame")
        self.frame.setFixedWidth(self._popup_width())
        self._apply_frame_stylesheet()
        main_layout.addWidget(self.frame)

        self.content_layout = QVBoxLayout(self.frame)
        self.content_layout.setContentsMargins(
            self._layout_tier.content_margin_left,
            self._layout_tier.content_margin_top,
            self._layout_tier.content_margin_right,
            self._layout_tier.content_margin_bottom,
        )
        self.content_layout.setSpacing(0)
        self.content_widget = None

        self.hide()
        self._configure_macos_window()

    @staticmethod
    def _current_tokens():
        return popup_tokens(config.popup_theme)

    def _current_layout_tier(self):
        return self._tokens.layout_tier(config.popup_layout)

    def _sync_layout_tier(self):
        self._tokens = self._current_tokens()
        self._layout_tier = self._current_layout_tier()
        base_font = QFont(self._tokens.font_family)
        base_font.setPixelSize(self._tokens.definition_font_size)
        self.setFont(base_font)
        self.layout().setContentsMargins(
            self._tokens.shadow_margin,
            self._tokens.shadow_margin,
            self._tokens.shadow_margin,
            self._tokens.shadow_margin,
        )
        self.frame.setFixedWidth(self._popup_width())
        self._apply_frame_stylesheet()
        self.content_layout.setContentsMargins(
            self._layout_tier.content_margin_left,
            self._layout_tier.content_margin_top,
            self._layout_tier.content_margin_right,
            self._layout_tier.content_margin_bottom,
        )

    def _popup_width(self) -> int:
        return self._layout_tier.width

    def _content_width(self) -> int:
        return self._layout_tier.content_width

    @staticmethod
    def _vocab_entries() -> int:
        return config.popup_vocab_entries

    @staticmethod
    def _senses_per_entry() -> int:
        return config.popup_senses_per_entry

    @staticmethod
    def _glosses_per_sense() -> int:
        return config.popup_glosses_per_sense

    def _apply_frame_stylesheet(self):
        self.frame.setStyleSheet(popup_frame_stylesheet(self._tokens))

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

    def get_latest_copy_text(self):
        return self._get_latest_top_entry_expression()

    def get_latest_jisho_query(self):
        return self._get_latest_top_entry_expression()

    def _get_latest_top_entry_expression(self):
        with self._data_lock:
            data = self._last_latest_data
        if not self.is_visible or config.is_paused:
            return None
        entry = self._top_visible_dictionary_entry(data)
        if not entry:
            return None
        return entry.written_form

    @staticmethod
    def _entries_from_data(data):
        if isinstance(data, LookupResult):
            return data.entries
        return data

    @staticmethod
    def _visible_kanji_characters(data, visible_vocab_entries: list[DictionaryEntry]) -> set[str]:
        sources = [entry.written_form for entry in visible_vocab_entries]
        if isinstance(data, LookupResult):
            lookup_text = data.lookup_text or (data.context.lookup_text if data.context else "")
            if lookup_text:
                sources.append(lookup_text)
        return {match.group(0) for source in sources for match in KANJI_REGEX.finditer(source or "")}

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
        self._sync_layout_tier()
        entries = self._entries_from_data(data)
        content_width = self._content_width()
        content = QWidget()
        content.setFixedWidth(content_width)
        content.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        content.setStyleSheet(transparent_stylesheet())

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        vocab_entries = [entry for entry in entries or [] if isinstance(entry, DictionaryEntry)]
        kanji_entries = [entry for entry in entries or [] if isinstance(entry, KanjiEntry)]
        visible_vocab_entries = vocab_entries[:self._vocab_entries()]

        hidden_sense_count = 0
        hidden_gloss_count = 0
        for index, entry in enumerate(visible_vocab_entries):
            if index > 0:
                layout.addWidget(self._separator())
            entry_widget, omitted_senses, omitted_glosses = self._dictionary_entry(entry)
            layout.addWidget(entry_widget)
            hidden_sense_count += omitted_senses
            hidden_gloss_count += omitted_glosses

        hidden_vocab_count = max(0, len(vocab_entries) - len(visible_vocab_entries))
        footer = self._omission_footer(hidden_vocab_count, hidden_sense_count, hidden_gloss_count)
        if footer:
            if layout.count() > 0:
                layout.addSpacing(self._tokens.footer_before_gap)
            layout.addWidget(footer)

        visible_kanji = self._visible_kanji_characters(data, visible_vocab_entries)
        visible_kanji_entries = [
            entry for entry in kanji_entries
            if not visible_kanji or entry.character in visible_kanji
        ]
        self._add_kanji_entries(layout, visible_kanji_entries)

        self._finalize_fixed_height(content)
        self._replace_content_widget(content)

    def _add_kanji_entries(self, layout: QVBoxLayout, entries: list[KanjiEntry]):
        if not entries:
            return

        presentation = self._layout_tier.kanji_presentation
        if presentation == "full":
            for entry in entries:
                if layout.count() > 0:
                    layout.addSpacing(self._tokens.kanji_before_gap)
                layout.addWidget(self._kanji_card(entry, include_details=True))
            return

        if layout.count() > 0:
            layout.addSpacing(self._tokens.kanji_before_gap)

        if presentation == "chip":
            layout.addWidget(self._kanji_chipline(entries))
        elif len(entries) == 1:
            layout.addWidget(self._kanji_card(entries[0], include_details=False))
        else:
            layout.addWidget(self._kanji_strip(entries))

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
        popup_width = self._popup_width()
        self.frame.setFixedSize(popup_width, height)
        self.setFixedSize(popup_width + self._tokens.shadow_margin * 2, height + self._tokens.shadow_margin * 2)

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
        font = QFont(self._tokens.font_family)
        font.setPixelSize(size)
        font.setWeight(weight)
        return font

    def _plain_label(
        self,
        text: str,
        color: str,
        size: int,
        weight: QFont.Weight = QFont.Weight.Normal,
        max_width: int | None = None,
    ) -> QLabel:
        if max_width is None:
            max_width = self._content_width()
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setFont(self._font(size, weight))
        label.setStyleSheet(plain_label_stylesheet(color, self._tokens))
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
        label.setStyleSheet(rich_label_stylesheet(color, size, self._tokens))
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        return label

    def _metadata_label(self, html: str, width: int | None = None, color: str | None = None) -> QLabel:
        if width is None:
            width = self._content_width()
        if color is None:
            color = self._tokens.metadata_text
        return self._rich_label(
            f'<span style="color:{color}; font-size:{self._tokens.metadata_font_size}px; line-height:125%;">{html}</span>',
            color,
            self._tokens.metadata_font_size,
            width,
        )

    def _flow_container(
        self,
        width: int | None = None,
        h_spacing: int = 7,
        v_spacing: int = 5,
    ) -> tuple[QWidget, FlowLayout]:
        if width is None:
            width = self._content_width()
        container = QWidget()
        container.setFixedWidth(width)
        container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        container.setStyleSheet(transparent_stylesheet())
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
            if len(shown_senses) >= self._senses_per_entry():
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
        return f' <span style="color:{self._tokens.metadata_label_text};">·</span> '.join(
            self._escape(value) for value in values if value
        )

    def _deconjugation_html(self, value: str) -> str:
        return (
            f'<span style="color:{self._tokens.deconjugation_text}; font-weight:700;">inflected</span>'
            f' <span style="color:{self._tokens.metadata_label_text};">·</span> {self._escape(value)}'
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
        return self._metadata_label(f'+ {" · ".join(parts)}', color=self._tokens.omission_text)

    def _entry_definition_parts(self, entry: DictionaryEntry) -> tuple[list[str], int, int]:
        sense_parts = []
        hidden_gloss_count = 0
        for sense in entry.senses:
            glosses = [self._gloss_to_html(gloss) for gloss in sense.get('glosses', []) if gloss]
            if not glosses:
                continue

            glosses_per_sense = self._glosses_per_sense()
            shown_glosses = glosses[:glosses_per_sense]
            hidden_gloss_count += max(0, len(glosses) - glosses_per_sense)
            sense_parts.append(", ".join(shown_glosses))

        senses_per_entry = self._senses_per_entry()
        hidden_sense_count = max(0, len(sense_parts) - senses_per_entry)
        return sense_parts[:senses_per_entry], hidden_sense_count, hidden_gloss_count

    def _numbered_definitions(self, sense_parts: list[str]) -> QWidget:
        content_width = self._content_width()
        container = QWidget()
        container.setFixedWidth(content_width)
        container.setStyleSheet(transparent_stylesheet())
        container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._tokens.definition_row_gap)

        number_width = self._tokens.definition_number_width
        text_width = content_width - number_width - self._tokens.definition_number_gap
        for index, sense_text in enumerate(sense_parts, 1):
            row = QWidget()
            row.setFixedWidth(content_width)
            row.setStyleSheet(transparent_stylesheet())
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(self._tokens.definition_number_gap)

            number = self._plain_label(
                str(index),
                self._tokens.sense_number_text,
                self._tokens.definition_font_size,
                QFont.Weight.DemiBold,
                number_width,
            )
            number.setFixedWidth(number_width)
            number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            row_layout.addWidget(number, 0, Qt.AlignmentFlag.AlignTop)
            row_layout.addWidget(self._rich_label(sense_text, self._tokens.definition_text, self._tokens.definition_font_size, text_width))
            self._finalize_fixed_height(row)
            layout.addWidget(row)

        self._finalize_fixed_height(container)
        return container

    def _dictionary_entry(self, entry: DictionaryEntry) -> tuple[QWidget, int, int]:
        content_width = self._content_width()
        entry_widget = QWidget()
        entry_widget.setFixedWidth(content_width)
        entry_widget.setStyleSheet(transparent_stylesheet())

        layout = QVBoxLayout(entry_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        row, row_layout = self._flow_container(h_spacing=8, v_spacing=2)
        row_layout.addWidget(self._plain_label(
            entry.written_form,
            self._tokens.word_text,
            self._tokens.word_font_size,
            QFont.Weight.DemiBold,
        ))
        if entry.reading:
            row_layout.addWidget(self._plain_label(
                f"[{entry.reading}]",
                self._tokens.reading_text,
                self._tokens.reading_font_size,
                QFont.Weight.Medium,
            ))
        self._finalize_flow_container(row, row_layout, content_width)
        layout.addWidget(row)

        metadata, deconj = self._entry_metadata(entry)
        shown_metadata = metadata if self._layout_tier.show_metadata else []
        shown_deconj = deconj if self._layout_tier.show_deconjugation else ""
        if shown_metadata:
            layout.addSpacing(self._tokens.entry_meta_gap)
            layout.addWidget(self._metadata_label(self._metadata_html(shown_metadata)))
        if shown_deconj:
            layout.addSpacing(self._tokens.entry_deconjugation_gap)
            layout.addWidget(self._metadata_label(self._deconjugation_html(shown_deconj), color=self._tokens.deconjugation_text))

        definition_parts, hidden_sense_count, hidden_gloss_count = self._entry_definition_parts(entry)
        if definition_parts:
            has_metadata = bool(shown_metadata or shown_deconj)
            layout.addSpacing(self._tokens.entry_definition_gap if has_metadata else self._tokens.entry_definition_gap_without_meta)
            layout.addWidget(self._numbered_definitions(definition_parts))

        self._finalize_fixed_height(entry_widget)
        return entry_widget, hidden_sense_count, hidden_gloss_count

    def _separator(self) -> QWidget:
        container = QWidget()
        container.setFixedWidth(self._content_width())
        container.setFixedHeight(13)
        container.setStyleSheet(transparent_stylesheet())

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(0)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(separator_stylesheet(self._tokens))
        layout.addWidget(line)
        return container

    def _kanji_chipline(self, entries: list[KanjiEntry]) -> QWidget:
        content_width = self._content_width()
        container, layout = self._flow_container(width=content_width, h_spacing=5, v_spacing=5)
        for entry in entries:
            chip = QFrame()
            chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            chip.setStyleSheet(
                f"background-color: {self._tokens.kanji_card_bg}; "
                f"border: 1px solid {self._tokens.kanji_card_border}; "
                "border-radius: 11px;"
            )
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(7, 4, 7, 4)
            chip_layout.setSpacing(4)
            chip_layout.addWidget(self._plain_label(
                entry.character,
                self._tokens.word_text,
                14,
                QFont.Weight.DemiBold,
                22,
            ))
            if entry.readings:
                chip_layout.addWidget(self._plain_label(
                    f"[{entry.readings[0]}]",
                    self._tokens.reading_text,
                    self._tokens.metadata_font_size,
                    QFont.Weight.DemiBold,
                    content_width,
                ))
            if entry.meanings:
                chip_layout.addWidget(self._plain_label(
                    entry.meanings[0],
                    self._tokens.muted_text,
                    self._tokens.metadata_font_size,
                    QFont.Weight.Normal,
                    content_width,
                ))
            self._finalize_fixed_height(chip)
            layout.addWidget(chip)
        self._finalize_flow_container(container, layout, content_width)
        return container

    def _kanji_strip(self, entries: list[KanjiEntry]) -> QWidget:
        content_width = self._content_width()
        container = QWidget()
        container.setFixedWidth(content_width)
        container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        container.setStyleSheet(transparent_stylesheet())

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        gap = 7
        column_width = (content_width - gap) // 2
        for row_start in range(0, len(entries), 2):
            row = QWidget()
            row.setFixedWidth(content_width)
            row.setStyleSheet(transparent_stylesheet())
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(gap)
            row_entries = entries[row_start:row_start + 2]
            cards = [self._kanji_mini_card(entry, column_width) for entry in row_entries]
            row_height = max((card.height() for card in cards), default=0)
            for card in cards:
                card.setFixedHeight(row_height)
                row_layout.addWidget(card)
            if len(row_entries) == 1:
                row_layout.addStretch(1)
            self._finalize_fixed_height(row)
            layout.addWidget(row)

        self._finalize_fixed_height(container)
        return container

    def _kanji_mini_card(self, entry: KanjiEntry, width: int) -> QFrame:
        card = QFrame()
        card.setFixedWidth(width)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        card.setStyleSheet(
            f"background-color: {self._tokens.kanji_card_bg}; "
            f"border: 1px solid {self._tokens.kanji_card_border}; "
            f"border-radius: {self._tokens.kanji_card_radius}px;"
        )

        layout = QHBoxLayout(card)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(7)

        glyph = QFrame()
        glyph.setFixedSize(38, 38)
        glyph.setStyleSheet(kanji_glyph_stylesheet(self._tokens))
        glyph_layout = QVBoxLayout(glyph)
        glyph_layout.setContentsMargins(0, 0, 0, 0)
        glyph_layout.setSpacing(0)
        glyph_label = self._plain_label(
            entry.character,
            self._tokens.word_text,
            26,
            QFont.Weight.DemiBold,
            38,
        )
        glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph_layout.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)

        body_width = width - 14 - 38 - 7
        body = QWidget()
        body.setFixedWidth(body_width)
        body.setStyleSheet(transparent_stylesheet())
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(2)

        readings = self._join_escaped(entry.readings)
        if readings:
            body_layout.addWidget(self._rich_label(
                f'<span style="color:{self._tokens.reading_text}; font-weight:700;">[{readings}]</span>',
                self._tokens.reading_text,
                self._tokens.metadata_font_size,
                body_width,
            ))
        meanings = self._join_escaped(entry.meanings[:3])
        if meanings:
            body_layout.addWidget(self._rich_label(meanings, self._tokens.muted_text, self._tokens.detail_font_size, body_width))

        self._finalize_fixed_height(body)
        layout.addWidget(body, 1)
        self._finalize_fixed_height(card)
        return card

    def _kanji_card(self, entry: KanjiEntry, include_details: bool) -> QFrame:
        content_width = self._content_width()
        card = QFrame()
        card.setObjectName("kanjiCard")
        card.setFixedWidth(content_width)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        card.setStyleSheet(kanji_card_stylesheet(self._tokens))

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(9)

        glyph = QFrame()
        glyph.setFixedSize(48, 48)
        glyph.setStyleSheet(kanji_glyph_stylesheet(self._tokens))
        glyph_layout = QVBoxLayout(glyph)
        glyph_layout.setContentsMargins(0, 0, 0, 0)
        glyph_layout.setSpacing(0)
        glyph_label = self._plain_label(
            entry.character,
            self._tokens.word_text,
            self._tokens.kanji_glyph_font_size,
            QFont.Weight.Medium,
            48,
        )
        glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph_layout.addWidget(glyph_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)

        right_width = content_width - 16 - 48 - 9
        details = QWidget()
        details.setFixedWidth(right_width)
        details.setStyleSheet(transparent_stylesheet())
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(0)

        readings = self._join_escaped(entry.readings)
        if readings:
            details_layout.addWidget(self._rich_label(
                f'<span style="color:{self._tokens.reading_text}; font-weight:700;">[{readings}]</span>',
                self._tokens.reading_text,
                self._tokens.kanji_reading_font_size,
                right_width,
            ))

        meanings = self._join_escaped(entry.meanings)
        if meanings:
            if details_layout.count() > 0:
                details_layout.addSpacing(self._tokens.kanji_body_row_gap)
            details_layout.addWidget(self._rich_label(meanings, self._tokens.definition_text, self._tokens.definition_font_size, right_width))

        if include_details:
            examples_html = self._kanji_examples_html(entry)
            components_html = self._kanji_components_html(entry)
            if examples_html or components_html:
                if details_layout.count() > 0:
                    details_layout.addSpacing(self._tokens.kanji_detail_top_gap)
                details_layout.addWidget(self._kanji_detail_block(examples_html, components_html, right_width))

        layout.addWidget(details, 1)
        self._finalize_fixed_height(card)
        return card

    def _kanji_detail_label(self, html: str, width: int) -> QTextBrowser:
        label = QTextBrowser()
        label.setFrameShape(QFrame.Shape.NoFrame)
        label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        label.setOpenExternalLinks(False)
        label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        label.setFixedWidth(width)
        label.setFont(self._font(self._tokens.detail_font_size))
        label.setStyleSheet(rich_label_stylesheet(self._tokens.muted_text, self._tokens.detail_font_size, self._tokens))
        label.setContentsMargins(0, 0, 0, 0)
        label.viewport().setStyleSheet(transparent_stylesheet())

        document = label.document()
        document.setDocumentMargin(0)
        document.setTextWidth(width)
        label.setHtml(
            f'<span style="color:{self._tokens.muted_text}; font-family:{self._tokens.font_stack_qss}; '
            f'font-size:{self._tokens.detail_font_size}px;">{html}</span>'
        )

        cursor = QTextCursor(document)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(
            self._tokens.kanji_detail_line_height_percent,
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
        )
        cursor.mergeBlockFormat(block_format)
        document.setTextWidth(width)

        label.setFixedHeight(math.ceil(document.size().height()))
        return label

    def _kanji_detail_row(self, label_text: str, html: str, width: int) -> QWidget:
        row = QWidget()
        row.setFixedWidth(width)
        row.setStyleSheet(transparent_stylesheet())
        row.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._tokens.kanji_detail_label_gap)

        label = self._plain_label(
            label_text,
            self._tokens.metadata_label_text,
            self._tokens.detail_font_size,
            QFont.Weight.DemiBold,
            self._tokens.kanji_detail_label_width,
        )
        label.setFixedWidth(self._tokens.kanji_detail_label_width)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)

        body_width = width - self._tokens.kanji_detail_label_width - self._tokens.kanji_detail_label_gap
        layout.addWidget(self._kanji_detail_label(html, body_width), 1, Qt.AlignmentFlag.AlignTop)

        self._finalize_fixed_height(row)
        return row

    def _kanji_detail_block(self, examples_html: str, components_html: str, width: int) -> QWidget:
        block = QWidget()
        block.setFixedWidth(width)
        block.setStyleSheet(transparent_stylesheet())
        block.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self._tokens.kanji_detail_row_gap)

        if examples_html:
            layout.addWidget(self._kanji_detail_row("ex", examples_html, width))
        if components_html:
            layout.addWidget(self._kanji_detail_row("parts", components_html, width))

        self._finalize_fixed_height(block)
        return block

    def _kanji_examples_html(self, entry: KanjiEntry) -> str:
        parts = []
        for ex in entry.examples:
            word = self._escape(ex.get('w', ''))
            reading = self._escape(ex.get('r', ''))
            meaning = self._escape(ex.get('m', ''))
            if word or reading or meaning:
                parts.append(
                    f'<span style="color:{self._tokens.detail_word_text}; font-weight:600;">{word}</span> '
                    f'<span style="color:{self._tokens.detail_reading_text};">[{reading}]</span> {meaning}'
                )
        if not parts:
            return ""
        return "; ".join(parts)

    def _kanji_components_html(self, entry: KanjiEntry) -> str:
        parts = []
        for component in entry.components:
            char = self._escape(component.get('c', ''))
            meaning = self._escape(component.get('m', ''))
            if meaning:
                parts.append(f'<span style="color:{self._tokens.detail_word_text}; font-weight:600;">{char}</span> {meaning}')
            elif char:
                parts.append(f'<span style="color:{self._tokens.detail_word_text}; font-weight:600;">{char}</span>')
        if not parts:
            return ""
        return " · ".join(parts)

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

    def hide_popup_for_external_navigation(self):
        with self._data_lock:
            self._latest_data = None
            self._last_latest_data = None
        if not self.is_visible:
            return
        self._auto_pause_media_triggered = False
        self._auto_pause_media_resume_deferred = False
        self._suppress_next_focus_restore = True
        self.hide()

    def hideEvent(self, event):
        was_visible = self.is_visible
        super().hideEvent(event)
        if not was_visible:
            return

        self.is_visible = False
        self._resume_auto_paused_media()
        QTimer.singleShot(50, lambda: self._release_lock_safely())
        if self._suppress_next_focus_restore:
            self._suppress_next_focus_restore = False
            self._previous_active_app_on_mac = None
        else:
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
        logger.debug("Popup: Re-applying popup styling and layout settings.")
        self._sync_layout_tier()
        self._apply_frame_stylesheet()
        with self._data_lock:
            data = self._last_latest_data or self._latest_data
        if data:
            self._set_entries(data)
        else:
            self._resize_to_content()
