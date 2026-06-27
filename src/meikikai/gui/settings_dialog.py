# meikikai/gui/settings_dialog.py
import logging

from PyQt6.QtCore import QObject, QLocale, QRectF, QSize, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from meikikai.config.config import (
    APP_NAME,
    DEFAULT_SHORTCUTS_TTS_SHORTCUT_NAME,
    MIN_AUTO_SCAN_INTERVAL_SECONDS,
    POPUP_GLOSSES_PER_SENSE_OPTIONS,
    POPUP_SENSES_PER_ENTRY_OPTIONS,
    POPUP_VOCAB_ENTRIES_OPTIONS,
    config,
)
from meikikai.gui.popup_design.tokens import DEFAULT_POPUP_THEME, POPUP_THEME_LABELS, popup_theme_label
from meikikai.gui.design import DIALOG, apply_dialog_style, dialog_title, separator, set_button_variant
from meikikai.gui.popup import Popup
from meikikai.gui.screen_ai_setup_dialog import ScreenAiSetupDialog
from meikikai.ocr.providers.chrome_screen_ai.component import get_screen_ai_status
from meikikai.tts.shortcuts import (
    ShortcutsTts,
    ShortcutsTtsCommandError,
    ShortcutsTtsEmptyOutputError,
    ShortcutsTtsError,
    ShortcutsTtsMissingShortcutError,
    ShortcutsTtsPlaybackError,
    ShortcutsTtsTimeoutError,
    cleanup_tts_file,
    play_caf,
    shortcut_exists,
)
from meikikai.utils.paths import paths


logger = logging.getLogger(__name__)
SETTINGS_DIALOG_MAX_INITIAL_HEIGHT = 700
SHORTCUTS_TTS_TEST_TEXT = "日本語の音声テストです。"


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
            background = QColor(*DIALOG.accent_rgb)
            border = QColor(75, 164, 255)
        else:
            background = QColor(*DIALOG.neutral_rgb, 13)
            border = QColor(*DIALOG.neutral_rgb, 88)

        if self.underMouse() or self.hasFocus():
            border = QColor(*DIALOG.accent_rgb, 190)

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
                QColor(DIALOG.accent_on),
                2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            ))
            painter.drawPath(check)


class ShortcutsTtsTestWorker(QObject):
    finished = pyqtSignal(bool, str, str, str)

    @pyqtSlot()
    def run(self):
        audio_path = None
        try:
            audio_path = ShortcutsTts().synthesize_to_caf(SHORTCUTS_TTS_TEST_TEXT)
            play_caf(audio_path)
        except ShortcutsTtsMissingShortcutError as e:
            self.finished.emit(False, "Shortcut not found", str(e), "warning")
            return
        except ShortcutsTtsEmptyOutputError as e:
            self.finished.emit(False, "No Shortcut audio", str(e), "warning")
            return
        except ShortcutsTtsTimeoutError as e:
            self.finished.emit(False, "Shortcuts TTS timed out", str(e), "warning")
            return
        except ShortcutsTtsPlaybackError as e:
            self.finished.emit(False, "Speech playback failed", str(e), "warning")
            return
        except ShortcutsTtsCommandError as e:
            self.finished.emit(False, "Shortcuts TTS failed", str(e), "warning")
            return
        except ShortcutsTtsError as e:
            self.finished.emit(False, "Shortcuts TTS failed", str(e), "warning")
            return
        except Exception:
            logger.exception("Unexpected Shortcuts TTS test failure.")
            self.finished.emit(
                False,
                "Shortcuts TTS failed",
                "Unexpected error while testing Shortcuts TTS. Check the MeikiKai log for details.",
                "critical",
            )
            return
        finally:
            cleanup_tts_file(audio_path)

        self.finished.emit(True, "Shortcuts TTS ready", "Played a sample with the configured Shortcut.", "success")


class ShortcutsTtsStatusWorker(QObject):
    finished = pyqtSignal(str, str)

    @pyqtSlot()
    def run(self):
        try:
            found = shortcut_exists()
        except ShortcutsTtsTimeoutError as e:
            self.finished.emit("warning", str(e))
            return
        except ShortcutsTtsError as e:
            self.finished.emit("warning", str(e))
            return
        except Exception:
            logger.exception("Unexpected Shortcuts TTS status check failure.")
            self.finished.emit(
                "warning",
                "Could not check Shortcuts. Check the MeikiKai log for details.",
            )
            return

        if found:
            self.finished.emit("ready", f"Found Shortcut named '{DEFAULT_SHORTCUTS_TTS_SHORTCUT_NAME}'.")
        else:
            self.finished.emit(
                "missing",
                f"No Shortcut named '{DEFAULT_SHORTCUTS_TTS_SHORTCUT_NAME}' was found. Create it in Shortcuts, then try again.",
            )


class SettingsDialog(QDialog):
    def __init__(self, popup_window: Popup, tray_icon, ocr_processor=None, parent=None):
        super().__init__(parent)
        self.popup_window = popup_window
        self.tray_icon = tray_icon
        self.ocr_processor = ocr_processor
        self._shortcuts_tts_test_thread = None
        self._shortcuts_tts_test_worker = None
        self._shortcuts_tts_status_thread = None
        self._shortcuts_tts_status_worker = None

        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setWindowIcon(QIcon(paths.get_resource_path('app_icon.icns')))
        self.setMinimumWidth(640)
        self._apply_window_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            DIALOG.window_margin_x,
            DIALOG.window_margin_top,
            DIALOG.window_margin_x,
            DIALOG.window_margin_bottom,
        )
        main_layout.setSpacing(0)

        main_layout.addWidget(dialog_title("Settings"))
        main_layout.addSpacing(DIALOG.title_gap)

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

        self.popup_theme_map = {label: key for key, label in POPUP_THEME_LABELS.items()}
        self.popup_theme_combo = QComboBox()
        self.popup_theme_combo.addItems(list(self.popup_theme_map.keys()))
        self.popup_theme_combo.setCurrentText(popup_theme_label(config.popup_theme))
        self._prepare_popup_control(self.popup_theme_combo)

        self.popup_layout_map = {
            "Compact": "compact",
            "Standard": "standard",
            "Complete": "complete",
        }
        self.popup_layout_combo = QComboBox()
        self.popup_layout_combo.addItems(list(self.popup_layout_map.keys()))
        current_layout_name = next(
            (k for k, v in self.popup_layout_map.items() if v == config.popup_layout), "Complete"
        )
        self.popup_layout_combo.setCurrentText(current_layout_name)
        self._prepare_popup_control(self.popup_layout_combo)

        self.popup_entries_combo = QComboBox()
        for value in POPUP_VOCAB_ENTRIES_OPTIONS:
            self.popup_entries_combo.addItem(str(value), value)
        self._set_combo_data(self.popup_entries_combo, config.popup_vocab_entries)
        self._prepare_popup_control(self.popup_entries_combo)

        self.popup_senses_combo = QComboBox()
        for value in POPUP_SENSES_PER_ENTRY_OPTIONS:
            self.popup_senses_combo.addItem(str(value), value)
        self._set_combo_data(self.popup_senses_combo, config.popup_senses_per_entry)
        self._prepare_popup_control(self.popup_senses_combo)

        self.popup_glosses_combo = QComboBox()
        for value in POPUP_GLOSSES_PER_SENSE_OPTIONS:
            self.popup_glosses_combo.addItem(str(value), value)
        self._set_combo_data(self.popup_glosses_combo, config.popup_glosses_per_sense)
        self._prepare_popup_control(self.popup_glosses_combo)

        self.popup_mode_map = {
            "Smart around cursor": "visual_novel_mode",
            "Lower right, flip at edges": "flip_both",
            "Right side, flip upward": "flip_vertically",
            "Below cursor, flip left": "flip_horizontally",
        }
        self.popup_position_combo = QComboBox()
        self.popup_position_combo.addItems(list(self.popup_mode_map.keys()))
        current_friendly_name = next(
            (k for k, v in self.popup_mode_map.items() if v == config.popup_position_mode), "Smart around cursor"
        )
        self.popup_position_combo.setCurrentText(current_friendly_name)
        self._prepare_popup_control(self.popup_position_combo)

        self.anki_connect_url_edit = QLineEdit(config.anki_connect_url)
        self.anki_connect_url_edit.setPlaceholderText("http://127.0.0.1:8765")
        self._prepare_text_control(self.anki_connect_url_edit, 246)

        self.anki_capture_screenshot_check = IndicatorCheckBox()
        self.anki_capture_screenshot_check.setChecked(config.anki_capture_screenshot)

        self.shortcuts_tts_enabled_check = IndicatorCheckBox()
        self.shortcuts_tts_enabled_check.setChecked(config.shortcuts_tts_enabled)

        self.shortcuts_tts_status_badge = QLabel("Unchecked")
        self.shortcuts_tts_status_badge.setTextFormat(Qt.TextFormat.PlainText)
        self.shortcuts_tts_status_refresh_button = QPushButton("Refresh")
        self.shortcuts_tts_status_refresh_button.setMinimumWidth(76)
        self.shortcuts_tts_status_refresh_button.clicked.connect(self.refresh_shortcuts_tts_status)
        self._set_shortcuts_tts_status("Unchecked", "warning", "Click Refresh to check for the configured Shortcut.")

        self.shortcuts_tts_test_button = QPushButton("Test voice")
        self.shortcuts_tts_test_button.setMinimumWidth(92)
        self.shortcuts_tts_test_button.clicked.connect(self.test_shortcuts_tts)

        self.anki_attach_tts_audio_check = IndicatorCheckBox()
        self.anki_attach_tts_audio_check.setChecked(config.anki_attach_tts_audio)

        self.screen_ai_status_badge = QLabel()
        self.screen_ai_status_badge.setTextFormat(Qt.TextFormat.PlainText)
        self.screen_ai_setup_button = QPushButton("Manage…")
        self.screen_ai_setup_button.clicked.connect(self.open_screen_ai_setup)
        self._update_screen_ai_status_badge()

        page_specs = [
            ("General", self._tab([
                self._section(
                    "Lookup",
                    [self._setting_row(
                        "Maximum lookup length",
                        "Characters kept from recognized text before lookup.",
                        self.max_lookup_spin,
                    )],
                ),
                self._section(
                    "Scanning",
                    [self._setting_row(
                        "Scan cooldown",
                        "Minimum delay between OCR scans.",
                        self.auto_scan_interval_spin,
                    )],
                ),
                self._section(
                    "OCR Engine",
                    [self._setting_row(
                        "Chrome Screen AI",
                        self._screen_ai_description(),
                        self._screen_ai_control(),
                    )],
                ),
            ])),
            ("Popup", self._tab([
                self._section(
                    "Display",
                    [
                        self._setting_row(
                            "Popup theme",
                            "Changes the popup palette while preserving layout and typography.",
                            self.popup_theme_combo,
                        ),
                        self._setting_row(
                            "Popup layout",
                            "Controls spacing, metadata shape, and kanji shape.",
                            self.popup_layout_combo,
                        ),
                        self._setting_row(
                            "Entries shown",
                            "Vocabulary entries shown before the omitted-entry footer.",
                            self.popup_entries_combo,
                        ),
                        self._setting_row(
                            "Senses per entry",
                            "Numbered definition groups shown for each vocabulary entry.",
                            self.popup_senses_combo,
                        ),
                        self._setting_row(
                            "Glosses per sense",
                            "Comma-separated translation glosses shown inside each sense.",
                            self.popup_glosses_combo,
                        ),
                        self._setting_row(
                            "Placement",
                            "Default side near the cursor; edge-aware modes stay on screen.",
                            self.popup_position_combo,
                        ),
                    ],
                ),
            ])),
            ("Anki", self._tab([
                self._section(
                    "Card export",
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
                ),
            ])),
            ("Speech", self._tab([
                self._section(
                    "Shortcuts TTS",
                    [
                        self._setting_row(
                            "Enable speech",
                            "Use a macOS Shortcut to generate local speech. The voice is selected inside the Shortcut.",
                            self.shortcuts_tts_enabled_check,
                        ),
                        self._setting_row(
                            "Shortcut status",
                            "Checks whether macOS Shortcuts can find the Meikikai Siri TTS Shortcut.",
                            self._shortcuts_tts_status_control(),
                        ),
                        self._setting_row(
                            "Test voice",
                            "Generates a short sample with the Meikikai Siri TTS Shortcut and plays the CAF output.",
                            self.shortcuts_tts_test_button,
                        ),
                        self._setting_row(
                            "Attach audio to Anki",
                            "Attach generated word speech to created Anki cards when TTS is enabled.",
                            self.anki_attach_tts_audio_check,
                        ),
                    ],
                ),
                self._section(
                    "Shortcut setup",
                    [
                        self._info_row(
                            "1",
                            f"Create a Shortcut named {DEFAULT_SHORTCUTS_TTS_SHORTCUT_NAME}."
                        ),
                        self._info_row(
                            "2",
                            "Set it to receive Text from Shortcut Input."
                        ),
                        self._info_row(
                            "3",
                            "Add Make Spoken Audio and choose a voice."
                        ),
                        self._info_row(
                            "4",
                            "Leave it final; no Stop and Output."
                        ),
                    ],
                ),
            ])),
            ("Shortcuts", self._tab([
                self._section(
                    "Popup shortcuts",
                    [
                        self._info_row(
                            "C",
                            "Copy the top entry expression."
                        ),
                        self._info_row(
                            "J",
                            "Search the top entry on Jisho.org."
                        ),
                        self._info_row(
                            "S",
                            "Speak the top entry reading or expression."
                        ),
                        self._info_row(
                            "A",
                            "Add the top entry to Anki."
                        ),
                    ],
                ),
            ])),
        ]
        main_layout.addWidget(self._segmented_page_selector(page_specs))
        main_layout.addSpacing(DIALOG.block_gap)
        main_layout.addWidget(self.settings_pages, 1)
        main_layout.addSpacing(DIALOG.footer_gap)

        footer = QHBoxLayout()
        footer.setSpacing(DIALOG.action_gap)
        footer.addStretch(1)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setMinimumWidth(76)
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save")
        set_button_variant(self.save_button, "primary")
        self.save_button.setMinimumWidth(76)
        self.save_button.clicked.connect(self.save_and_accept)
        self.save_button.setDefault(True)
        footer.addWidget(self.save_button)
        main_layout.addLayout(footer)

        self.resize(
            self.minimumWidth(),
            min(self.sizeHint().height(), SETTINGS_DIALOG_MAX_INITIAL_HEIGHT),
        )
        self.refresh_shortcuts_tts_status()

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

    def test_shortcuts_tts(self):
        if self._is_shortcuts_tts_busy():
            return

        self._shortcuts_tts_test_thread = QThread(self)
        self._shortcuts_tts_test_worker = ShortcutsTtsTestWorker()
        self._shortcuts_tts_test_worker.moveToThread(self._shortcuts_tts_test_thread)
        self._shortcuts_tts_test_thread.started.connect(self._shortcuts_tts_test_worker.run)
        self._shortcuts_tts_test_worker.finished.connect(self._handle_shortcuts_tts_test_finished)
        self._shortcuts_tts_test_worker.finished.connect(self._shortcuts_tts_test_thread.quit)
        self._shortcuts_tts_test_worker.finished.connect(self._shortcuts_tts_test_worker.deleteLater)
        self._shortcuts_tts_test_thread.finished.connect(self._shortcuts_tts_test_thread.deleteLater)
        self._shortcuts_tts_test_thread.finished.connect(self._clear_shortcuts_tts_test_worker)
        self._update_shortcuts_tts_busy_controls()
        self._shortcuts_tts_test_thread.start()

    def refresh_shortcuts_tts_status(self):
        if self._is_shortcuts_tts_busy():
            return

        self._set_shortcuts_tts_status(
            "Checking",
            "warning",
            f"Checking for Shortcut named '{DEFAULT_SHORTCUTS_TTS_SHORTCUT_NAME}'.",
        )
        self._shortcuts_tts_status_thread = QThread(self)
        self._shortcuts_tts_status_worker = ShortcutsTtsStatusWorker()
        self._shortcuts_tts_status_worker.moveToThread(self._shortcuts_tts_status_thread)
        self._shortcuts_tts_status_thread.started.connect(self._shortcuts_tts_status_worker.run)
        self._shortcuts_tts_status_worker.finished.connect(self._handle_shortcuts_tts_status_finished)
        self._shortcuts_tts_status_worker.finished.connect(self._shortcuts_tts_status_thread.quit)
        self._shortcuts_tts_status_worker.finished.connect(self._shortcuts_tts_status_worker.deleteLater)
        self._shortcuts_tts_status_thread.finished.connect(self._shortcuts_tts_status_thread.deleteLater)
        self._shortcuts_tts_status_thread.finished.connect(self._clear_shortcuts_tts_status_worker)
        self._update_shortcuts_tts_busy_controls()
        self._shortcuts_tts_status_thread.start()

    @pyqtSlot(bool, str, str, str)
    def _handle_shortcuts_tts_test_finished(self, _success: bool, title: str, message: str, level: str):
        self._update_shortcuts_tts_busy_controls()
        if self.tray_icon:
            self.tray_icon.show_status_message(title, message, level)

    @pyqtSlot(str, str)
    def _handle_shortcuts_tts_status_finished(self, state: str, message: str):
        if state == "ready":
            self._set_shortcuts_tts_status("Found", "ready", message)
        elif state == "missing":
            self._set_shortcuts_tts_status("Missing", "warning", message)
        else:
            self._set_shortcuts_tts_status("Error", "warning", message)
        self._update_shortcuts_tts_busy_controls()

    def _clear_shortcuts_tts_test_worker(self):
        self._shortcuts_tts_test_thread = None
        self._shortcuts_tts_test_worker = None
        self._update_shortcuts_tts_busy_controls()

    def _clear_shortcuts_tts_status_worker(self):
        self._shortcuts_tts_status_thread = None
        self._shortcuts_tts_status_worker = None
        self._update_shortcuts_tts_busy_controls()

    def _shortcuts_tts_status_control(self):
        control = QWidget()
        layout = QHBoxLayout(control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(DIALOG.action_gap)
        layout.addWidget(self.shortcuts_tts_status_badge)
        layout.addWidget(self.shortcuts_tts_status_refresh_button)
        return control

    def _set_shortcuts_tts_status(self, text: str, state: str, tooltip: str):
        self.shortcuts_tts_status_badge.setText(text)
        self.shortcuts_tts_status_badge.setToolTip(tooltip)
        self.shortcuts_tts_status_badge.setObjectName("statusBadgeReady" if state == "ready" else "statusBadgeWarning")
        self.shortcuts_tts_status_badge.style().unpolish(self.shortcuts_tts_status_badge)
        self.shortcuts_tts_status_badge.style().polish(self.shortcuts_tts_status_badge)

    def _is_shortcuts_tts_test_running(self):
        return bool(self._shortcuts_tts_test_thread and self._shortcuts_tts_test_thread.isRunning())

    def _is_shortcuts_tts_status_running(self):
        return bool(self._shortcuts_tts_status_thread and self._shortcuts_tts_status_thread.isRunning())

    def _is_shortcuts_tts_busy(self):
        return self._is_shortcuts_tts_test_running() or self._is_shortcuts_tts_status_running()

    def _update_shortcuts_tts_busy_controls(self):
        test_busy = self._is_shortcuts_tts_test_running()
        status_busy = self._is_shortcuts_tts_status_running()
        busy = test_busy or status_busy
        self.shortcuts_tts_test_button.setText("Testing…" if test_busy else "Test voice")
        self.shortcuts_tts_status_refresh_button.setText("Checking…" if status_busy else "Refresh")
        self.shortcuts_tts_test_button.setEnabled(not busy)
        self.shortcuts_tts_status_refresh_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)

    def _screen_ai_control(self):
        control = QWidget()
        layout = QHBoxLayout(control)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(DIALOG.action_gap)
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
        apply_dialog_style(self, f"""
            QWidget#settingsSegmentedRow {{
                background-color: transparent;
            }}
            QFrame#settingsSegmentedControl {{
                background-color: {DIALOG.control_bg};
                border: 1px solid {DIALOG.control_border};
                border-radius: 9px;
            }}
            QPushButton#settingsSegmentButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 7px;
                color: {DIALOG.text_muted};
                font-weight: 650;
                margin: 0;
                min-height: 24px;
                padding: 3px 12px;
            }}
            QPushButton#settingsSegmentButton:hover {{
                background-color: {DIALOG.control_bg_hover};
                color: {DIALOG.text};
            }}
            QPushButton#settingsSegmentButton[selected="true"] {{
                background-color: {DIALOG.accent_tint};
                border-color: {DIALOG.accent_tint_border};
                color: {DIALOG.accent_soft_text};
            }}
            QStackedWidget#settingsPages,
            QWidget#settingsTabPage {{
                background-color: transparent;
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

    def _set_combo_data(self, combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _segmented_page_selector(self, page_specs):
        row = QWidget()
        row.setObjectName("settingsSegmentedRow")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        segmented = QFrame()
        segmented.setObjectName("settingsSegmentedControl")
        segmented.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        segmented_layout = QHBoxLayout(segmented)
        segmented_layout.setContentsMargins(2, 2, 2, 2)
        segmented_layout.setSpacing(2)

        self.settings_page_buttons = []
        self.settings_pages = QStackedWidget()
        self.settings_pages.setObjectName("settingsPages")

        for index, (label, page) in enumerate(page_specs):
            button = QPushButton(label)
            button.setObjectName("settingsSegmentButton")
            button.setCheckable(True)
            button.setProperty("selected", False)
            button.clicked.connect(lambda checked=False, page_index=index: self._select_settings_page(page_index))
            segmented_layout.addWidget(button)
            self.settings_page_buttons.append(button)
            self.settings_pages.addWidget(page)

        row_layout.addWidget(segmented)
        row_layout.addStretch(1)
        self._select_settings_page(0)
        return row

    def _select_settings_page(self, index: int):
        self.settings_pages.setCurrentIndex(index)
        for button_index, button in enumerate(self.settings_page_buttons):
            selected = button_index == index
            button.setChecked(selected)
            button.setProperty("selected", selected)
            button.style().unpolish(button)
            button.style().polish(button)

    def _tab(self, sections):
        tab = QWidget()
        tab.setObjectName("settingsTabPage")
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, DIALOG.block_gap, 0, 0)
        layout.setSpacing(DIALOG.section_gap)
        for section in sections:
            layout.addWidget(section)
        layout.addStretch(1)
        return tab

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
        section_layout.addSpacing(DIALOG.section_label_gap)

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
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(
            DIALOG.row_padding_x,
            DIALOG.row_padding_y,
            DIALOG.row_padding_x,
            DIALOG.row_padding_y,
        )
        row_layout.setSpacing(DIALOG.row_gap)

        text_column = QWidget()
        text_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
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
        description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_column_layout.addWidget(description_label)

        row_layout.addWidget(text_column, 1)
        row_layout.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return row

    def _info_row(self, shortcut, text, min_text_lines: int = 1):
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(
            DIALOG.row_padding_x,
            DIALOG.row_padding_y,
            DIALOG.row_padding_x,
            DIALOG.row_padding_y,
        )
        row_layout.setSpacing(DIALOG.row_gap)

        shortcut_label = QLabel(shortcut)
        shortcut_label.setObjectName("infoShortcut")
        shortcut_label.setTextFormat(Qt.TextFormat.PlainText)
        shortcut_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_layout.addWidget(shortcut_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        label = QLabel(text)
        label.setObjectName("infoText")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if min_text_lines > 1:
            text_height = label.fontMetrics().lineSpacing() * min_text_lines + 4
            label.setMinimumHeight(text_height)
            row.setMinimumHeight(DIALOG.row_padding_y * 2 + text_height)
        row_layout.addWidget(label, 1)
        return row

    def _separator(self):
        return separator()

    def save_and_accept(self):
        if self._is_shortcuts_tts_busy():
            return

        config.max_lookup_length = self.max_lookup_spin.value()
        config.auto_scan_interval_seconds = self.auto_scan_interval_spin.value()

        selected_theme_name = self.popup_theme_combo.currentText()
        config.popup_theme = self.popup_theme_map.get(selected_theme_name, DEFAULT_POPUP_THEME)

        selected_layout_name = self.popup_layout_combo.currentText()
        config.popup_layout = self.popup_layout_map.get(selected_layout_name, "complete")
        config.popup_vocab_entries = int(self.popup_entries_combo.currentData())
        config.popup_senses_per_entry = int(self.popup_senses_combo.currentData())
        config.popup_glosses_per_sense = int(self.popup_glosses_combo.currentData())

        selected_friendly_name = self.popup_position_combo.currentText()
        config.popup_position_mode = self.popup_mode_map.get(selected_friendly_name, "visual_novel_mode")
        config.anki_connect_url = self.anki_connect_url_edit.text().strip() or "http://127.0.0.1:8765"
        config.anki_capture_screenshot = self.anki_capture_screenshot_check.isChecked()
        config.shortcuts_tts_enabled = self.shortcuts_tts_enabled_check.isChecked()
        config.anki_attach_tts_audio = self.anki_attach_tts_audio_check.isChecked()
        config.save()

        self.popup_window.reapply_settings()
        self.tray_icon.reapply_settings()
        self.popup_window.shared_state.screenshot_trigger_event.set()

        self.accept()

    def reject(self):
        if self._is_shortcuts_tts_busy():
            return
        super().reject()
