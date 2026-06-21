# meikikai/gui/settings_dialog.py
from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from meikikai.config.config import config, APP_NAME
from meikikai.gui.popup import Popup
from meikikai.ocr.ocr import OcrProcessor
from meikikai.utils.paths import paths

FONT_STACK_QSS = '"SF Pro Text", "Helvetica Neue", "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif'
DIALOG_BG = "#20232b"
PANEL_BG = "rgba(237, 241, 247, 9)"
PANEL_BORDER = "rgba(237, 241, 247, 24)"
SEPARATOR_COLOR = "rgba(237, 241, 247, 18)"
TEXT_COLOR = "#edf1f7"
MUTED_COLOR = "#a8b0c2"


class DecimalSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLocale(QLocale.c())

    def validate(self, text, pos):
        return super().validate(text.replace(",", "."), pos)

    def valueFromText(self, text):
        return super().valueFromText(text.replace(",", "."))


class SettingsDialog(QDialog):
    def __init__(self, ocr_processor: OcrProcessor, popup_window: Popup, tray_icon, parent=None):
        super().__init__(parent)
        self.ocr_processor = ocr_processor
        self.popup_window = popup_window
        self.tray_icon = tray_icon

        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setWindowIcon(QIcon(paths.get_resource_path('app_icon.icns')))
        self.setMinimumWidth(508)
        self._apply_window_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 20)
        main_layout.setSpacing(0)

        self.max_lookup_spin = QSpinBox()
        self.max_lookup_spin.setRange(5, 100)
        self.max_lookup_spin.setValue(config.max_lookup_length)
        self._prepare_numeric_control(self.max_lookup_spin, 64)

        self.auto_scan_interval_spin = DecimalSpinBox()
        self.auto_scan_interval_spin.setRange(0.0, 60.0)
        self.auto_scan_interval_spin.setDecimals(1)
        self.auto_scan_interval_spin.setSingleStep(0.1)
        self.auto_scan_interval_spin.setValue(config.auto_scan_interval_seconds)
        self.auto_scan_interval_spin.setSuffix(" s")
        self.auto_scan_interval_spin.setToolTip(
            "Minimum time between OCR scans\nCan reduce system load, but worsens perceived latency")
        self._prepare_numeric_control(self.auto_scan_interval_spin, 76)

        self.popup_mode_map = {
            "Visual Novel Mode": "visual_novel_mode",
            "Flip Both": "flip_both",
            "Flip Vertically": "flip_vertically",
            "Flip Horizontally": "flip_horizontally",
        }
        self.popup_position_combo = QComboBox()
        self.popup_position_combo.addItems(list(self.popup_mode_map.keys()))
        current_friendly_name = next(
            (k for k, v in self.popup_mode_map.items() if v == config.popup_position_mode), "Visual Novel Mode"
        )
        self.popup_position_combo.setCurrentText(current_friendly_name)
        self._prepare_popup_control(self.popup_position_combo)

        main_layout.addWidget(self._section(
            "Lookup",
            [self._setting_row(
                "Maximum lookup length",
                "Characters kept from recognized text before lookup.",
                self.max_lookup_spin,
            )],
        ))
        main_layout.addSpacing(14)
        main_layout.addWidget(self._section(
            "Scanning",
            [self._setting_row(
                "Scan cooldown",
                "Minimum delay between OCR scans.",
                self.auto_scan_interval_spin,
            )],
        ))
        main_layout.addSpacing(14)
        main_layout.addWidget(self._section(
            "Popup",
            [self._setting_row(
                "Placement",
                "Where the popup appears near the cursor.",
                self.popup_position_combo,
            )],
        ))

        main_layout.addSpacing(22)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button:
            save_button.setDefault(True)
        main_layout.addWidget(buttons, 0, Qt.AlignmentFlag.AlignRight)

        self.resize(self.minimumWidth(), self.sizeHint().height())

    def _apply_window_style(self):
        base_font = QFont("SF Pro Text")
        base_font.setPixelSize(13)
        self.setFont(base_font)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DIALOG_BG};
                color: {TEXT_COLOR};
                font-family: {FONT_STACK_QSS};
                font-size: 13px;
            }}
            QLabel#sectionLabel {{
                color: {TEXT_COLOR};
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.2px;
            }}
            QLabel#settingTitle {{
                color: {TEXT_COLOR};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#settingDescription {{
                color: {MUTED_COLOR};
                font-size: 11px;
            }}
            QFrame#settingsPanel {{
                background-color: {PANEL_BG};
                border: 1px solid {PANEL_BORDER};
                border-radius: 12px;
            }}
            QFrame#rowSeparator {{
                background-color: {SEPARATOR_COLOR};
                border: none;
            }}
            QSpinBox,
            QDoubleSpinBox {{
                background-color: rgba(237, 241, 247, 13);
                border: 1px solid rgba(237, 241, 247, 22);
                border-radius: 7px;
                color: {TEXT_COLOR};
                padding: 3px 8px;
                selection-background-color: #0a84ff;
            }}
            QSpinBox:focus,
            QDoubleSpinBox:focus {{
                border-color: rgba(10, 132, 255, 190);
            }}
        """)

    def _prepare_numeric_control(self, control, width):
        control.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        control.setFixedWidth(width)
        control.setAlignment(Qt.AlignmentFlag.AlignRight)
        control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _prepare_popup_control(self, control):
        control.setFixedWidth(188)
        control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _section(self, title, rows):
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)

        section_label = QLabel(title)
        section_label.setObjectName("sectionLabel")
        section_label.setTextFormat(Qt.TextFormat.PlainText)
        section_label.setFixedHeight(18)
        section_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        section_layout.addWidget(section_label)
        section_layout.addSpacing(8)

        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        for index, row in enumerate(rows):
            if index:
                panel_layout.addWidget(self._separator())
            panel_layout.addWidget(row)

        section_layout.addWidget(panel)
        return section

    def _setting_row(self, title, description, control):
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 9, 14, 9)
        row_layout.setSpacing(18)

        text_column = QWidget()
        text_column_layout = QVBoxLayout(text_column)
        text_column_layout.setContentsMargins(0, 0, 0, 0)
        text_column_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("settingTitle")
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        title_label.setBuddy(control)
        text_column_layout.addWidget(title_label)

        description_label = QLabel(description)
        description_label.setObjectName("settingDescription")
        description_label.setTextFormat(Qt.TextFormat.PlainText)
        description_label.setWordWrap(True)
        text_column_layout.addWidget(description_label)

        row_layout.addWidget(text_column, 1)
        row_layout.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return row

    def _separator(self):
        separator = QFrame()
        separator.setObjectName("rowSeparator")
        separator.setFixedHeight(1)
        return separator

    def save_and_accept(self):
        config.max_lookup_length = self.max_lookup_spin.value()
        config.auto_scan_interval_seconds = self.auto_scan_interval_spin.value()

        selected_friendly_name = self.popup_position_combo.currentText()
        config.popup_position_mode = self.popup_mode_map.get(selected_friendly_name, "visual_novel_mode")
        config.save()

        self.popup_window.reapply_settings()
        self.tray_icon.reapply_settings()
        self.ocr_processor.shared_state.screenshot_trigger_event.set()

        self.accept()
