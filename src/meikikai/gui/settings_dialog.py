# meikikai/gui/settings_dialog.py
from PyQt6.QtCore import QLocale, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from meikikai.config.config import APP_NAME, MIN_AUTO_SCAN_INTERVAL_SECONDS, config
from meikikai.gui.popup import Popup
from meikikai.gui.screen_ai_setup_dialog import ScreenAiSetupDialog
from meikikai.ocr.providers.chrome_screen_ai.component import get_screen_ai_status
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


class IndicatorCheckBox(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(22, 22)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(22, 22)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(2, 2, 18, 18)
        if self.isChecked():
            background = QColor("#0a84ff")
            border = QColor(75, 164, 255)
        else:
            background = QColor(237, 241, 247, 13)
            border = QColor(237, 241, 247, 88)

        if self.underMouse() or self.hasFocus():
            border = QColor(10, 132, 255, 190)

        painter.setBrush(background)
        painter.setPen(QPen(border, 1.5))
        painter.drawRoundedRect(rect, 5, 5)

        if self.isChecked():
            check = QPainterPath()
            check.moveTo(6.7, 11.0)
            check.lineTo(9.4, 13.7)
            check.lineTo(15.6, 7.4)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(
                QColor("#ffffff"),
                2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            ))
            painter.drawPath(check)


class SettingsDialog(QDialog):
    def __init__(self, popup_window: Popup, tray_icon, ocr_processor=None, parent=None):
        super().__init__(parent)
        self.popup_window = popup_window
        self.tray_icon = tray_icon
        self.ocr_processor = ocr_processor

        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setWindowIcon(QIcon(paths.get_resource_path('app_icon.icns')))
        self.setMinimumWidth(508)
        self._apply_window_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 20, 18, 20)
        main_layout.setSpacing(0)

        title_label = QLabel("Settings")
        title_label.setObjectName("dialogTitle")
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title_label.setFixedHeight(28)
        main_layout.addWidget(title_label)
        main_layout.addSpacing(12)

        self.max_lookup_spin = QSpinBox()
        self.max_lookup_spin.setRange(5, 100)
        self.max_lookup_spin.setValue(config.max_lookup_length)
        self._prepare_numeric_control(self.max_lookup_spin, 64)

        self.auto_scan_interval_spin = DecimalSpinBox()
        self.auto_scan_interval_spin.setRange(MIN_AUTO_SCAN_INTERVAL_SECONDS, 60.0)
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

        self.anki_connect_url_edit = QLineEdit(config.anki_connect_url)
        self.anki_connect_url_edit.setPlaceholderText("http://127.0.0.1:8765")
        self._prepare_text_control(self.anki_connect_url_edit, 246)

        self.anki_capture_screenshot_check = IndicatorCheckBox()
        self.anki_capture_screenshot_check.setChecked(config.anki_capture_screenshot)

        self.screen_ai_status_badge = QLabel()
        self.screen_ai_status_badge.setTextFormat(Qt.TextFormat.PlainText)
        self.screen_ai_setup_button = QPushButton("Manage…")
        self.screen_ai_setup_button.setObjectName("primaryButton")
        self.screen_ai_setup_button.clicked.connect(self.open_screen_ai_setup)
        self._update_screen_ai_status_badge()

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
        main_layout.addSpacing(14)
        main_layout.addWidget(self._section(
            "OCR Engine",
            [self._setting_row(
                "Chrome Screen AI",
                self._screen_ai_description(),
                self._screen_ai_control(),
            )],
        ))
        main_layout.addSpacing(14)
        main_layout.addWidget(self._section(
            "Anki",
            [
                self._setting_row(
                    "AnkiConnect URL",
                    "Local AnkiConnect endpoint used for direct card creation.",
                    self.anki_connect_url_edit,
                ),
                self._setting_row(
                    "Capture screenshot",
                    "Prompt for a native macOS crop when adding a card. Esc cancels card creation; disable this to add cards without screenshots.",
                    self.anki_capture_screenshot_check,
                ),
            ],
        ))
        main_layout.addSpacing(14)
        main_layout.addWidget(self._section(
            "Shortcuts",
            [
                self._info_row(
                    "Ctrl+Shift+C",
                    "While the popup is visible, copies the top entry expression to the clipboard."
                ),
                self._info_row(
                    "Ctrl+Shift+J",
                    "While the popup is visible, opens a Jisho.org search for the top entry expression."
                ),
                self._info_row(
                    "Ctrl+Shift+M",
                    "While the popup is visible, adds the top entry to Anki. "
                    "Deck and note type setup is automatic; duplicate words are skipped."
                ),
            ],
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

    def _screen_ai_description(self):
        status = get_screen_ai_status()
        if self.ocr_processor and self.ocr_processor.is_backend_available():
            return "Ready. Downloaded separately from Google/Chromium; manage install, notices, or uninstall."
        if status.installed:
            return "Installed, but OCR is not loaded. Open Manage to reinstall/update or view details."
        return "Required for OCR. Downloaded separately from Google/Chromium only after you choose Download."

    def open_screen_ai_setup(self):
        setup_dialog = ScreenAiSetupDialog(
            self.ocr_processor,
            tray_icon=self.tray_icon,
            setup_required=not bool(self.ocr_processor and self.ocr_processor.is_backend_available()),
            parent=self,
        )
        setup_dialog.exec()
        self._update_screen_ai_status_badge()
        self.tray_icon.reapply_settings()

    def _screen_ai_control(self):
        control = QWidget()
        layout = QHBoxLayout(control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.screen_ai_status_badge)
        layout.addWidget(self.screen_ai_setup_button)
        return control

    def _update_screen_ai_status_badge(self):
        status = get_screen_ai_status()
        ready = bool(self.ocr_processor and self.ocr_processor.is_backend_available())
        if ready:
            self.screen_ai_status_badge.setText("Ready")
            self.screen_ai_status_badge.setObjectName("statusBadgeReady")
        elif status.installed:
            self.screen_ai_status_badge.setText("Reload")
            self.screen_ai_status_badge.setObjectName("statusBadgeWarning")
        else:
            self.screen_ai_status_badge.setText("Missing")
            self.screen_ai_status_badge.setObjectName("statusBadgeWarning")
        self.screen_ai_status_badge.style().unpolish(self.screen_ai_status_badge)
        self.screen_ai_status_badge.style().polish(self.screen_ai_status_badge)

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
            QLabel#dialogTitle {{
                color: {TEXT_COLOR};
                font-size: 20px;
                font-weight: 800;
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
            QLabel#infoShortcut {{
                background-color: rgba(10, 132, 255, 32);
                border: 1px solid rgba(10, 132, 255, 76);
                border-radius: 6px;
                color: #c8e1ff;
                font-size: 11px;
                font-weight: 700;
                padding: 3px 7px;
            }}
            QLabel#infoText {{
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
            QDoubleSpinBox,
            QLineEdit {{
                background-color: rgba(237, 241, 247, 13);
                border: 1px solid rgba(237, 241, 247, 22);
                border-radius: 7px;
                color: {TEXT_COLOR};
                padding: 3px 8px;
                selection-background-color: #0a84ff;
            }}
            QSpinBox:focus,
            QDoubleSpinBox:focus,
            QLineEdit:focus {{
                border-color: rgba(10, 132, 255, 190);
            }}
            QPushButton#primaryButton {{
                background-color: #0a84ff;
                border: 1px solid rgba(123, 193, 255, 170);
                border-radius: 7px;
                color: #ffffff;
                font-weight: 650;
                min-height: 24px;
                padding: 3px 10px;
            }}
            QPushButton#primaryButton:hover {{
                background-color: #2492ff;
            }}
            QPushButton#primaryButton:pressed {{
                background-color: #006edb;
            }}
            QLabel#statusBadgeReady,
            QLabel#statusBadgeWarning {{
                border-radius: 7px;
                font-size: 10px;
                font-weight: 750;
                padding: 3px 7px;
            }}
            QLabel#statusBadgeReady {{
                background-color: rgba(48, 209, 88, 18);
                border: 1px solid rgba(48, 209, 88, 70);
                color: #9be7ae;
            }}
            QLabel#statusBadgeWarning {{
                background-color: rgba(255, 204, 0, 10);
                border: 1px solid rgba(255, 204, 0, 44);
                color: #e8c762;
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

    def _prepare_text_control(self, control, width):
        control.setFixedWidth(width)
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

    def _info_row(self, shortcut, text):
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 10, 14, 12)
        row_layout.setSpacing(18)

        shortcut_label = QLabel(shortcut)
        shortcut_label.setObjectName("infoShortcut")
        shortcut_label.setTextFormat(Qt.TextFormat.PlainText)
        shortcut_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_layout.addWidget(shortcut_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        label = QLabel(text)
        label.setObjectName("infoText")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout.addWidget(label, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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
        config.anki_connect_url = self.anki_connect_url_edit.text().strip() or "http://127.0.0.1:8765"
        config.anki_capture_screenshot = self.anki_capture_screenshot_check.isChecked()
        config.save()

        self.popup_window.reapply_settings()
        self.tray_icon.reapply_settings()
        self.popup_window.shared_state.screenshot_trigger_event.set()

        self.accept()
