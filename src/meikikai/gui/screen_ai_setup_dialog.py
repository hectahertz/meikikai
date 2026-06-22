from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from meikikai.config.config import APP_NAME
from meikikai.ocr.providers.chrome_screen_ai.component import (
    CIPD_SOURCE_LABEL,
    ScreenAiComponentStatus,
    get_screen_ai_status,
    install_screen_ai_from_cipd,
    screen_ai_install_dir,
    uninstall_screen_ai,
)
from meikikai.utils.paths import paths

FONT_STACK_QSS = '"SF Pro Text", "Helvetica Neue", "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif'
DIALOG_BG = "#20232b"
PANEL_BG = "rgba(237, 241, 247, 9)"
PANEL_BORDER = "rgba(237, 241, 247, 24)"
TEXT_COLOR = "#edf1f7"
MUTED_COLOR = "#a8b0c2"
SUBTLE_COLOR = "#7f8797"
APPROX_INSTALLED_SIZE = "about 125 MB"
DIALOG_TITLE_HEIGHT = 28


def _display_path(path: str | Path) -> str:
    text = str(path)
    home = str(Path.home())
    if text == home:
        return "~"
    if text.startswith(f"{home}/"):
        return f"~/{text[len(home) + 1:]}"
    return text


class ScreenAiInstallWorker(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object, object)

    @pyqtSlot()
    def run(self):
        try:
            status = install_screen_ai_from_cipd(self.progress.emit)
        except Exception as e:
            self.finished.emit(None, str(e))
            return

        self.finished.emit(status, None)


class ScreenAiDownloadConfirmDialog(QDialog):
    def __init__(self, installed: bool, parent=None):
        super().__init__(parent)
        self.installed = installed
        self.setWindowTitle("Reinstall/update Chrome Screen AI?" if installed else "Download Chrome Screen AI?")
        self.setWindowIcon(QIcon(paths.get_resource_path('app_icon.icns')))
        self.setFixedWidth(560)
        self._apply_window_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 20, 18, 16)
        main_layout.setSpacing(12)

        title_label = QLabel("Reinstall/update Chrome Screen AI?" if installed else "Download Chrome Screen AI?")
        title_label.setObjectName("dialogTitle")
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        title_label.setWordWrap(False)
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title_label.setFixedHeight(DIALOG_TITLE_HEIGHT)
        main_layout.addWidget(title_label)

        subtitle = QLabel(
            "MeikiKai will download and install this OCR component from Google/Chromium public infrastructure."
        )
        subtitle.setObjectName("confirmBody")
        subtitle.setTextFormat(Qt.TextFormat.PlainText)
        subtitle.setWordWrap(True)
        subtitle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(subtitle)

        bullets = QWidget()
        bullets.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bullets_layout = QVBoxLayout(bullets)
        bullets_layout.setContentsMargins(0, 0, 4, 0)
        bullets_layout.setSpacing(4)
        bullets_layout.addWidget(self._bullet_row(
            "Third-party component from Google/Chromium; not bundled with or developed by MeikiKai, "
            "and MeikiKai is not affiliated with Google or Chromium."
        ))
        bullets_layout.addWidget(self._bullet_row("Experimental for this use."))
        bullets_layout.addWidget(self._bullet_row("Removable at any time from Settings."))
        main_layout.addWidget(bullets)

        details_panel = QFrame()
        details_panel.setObjectName("detailsPanel")
        details_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        details_layout = QVBoxLayout(details_panel)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_layout.setSpacing(4)

        destination_label = QLabel("Install location")
        destination_label.setObjectName("detailTitle")
        destination_label.setTextFormat(Qt.TextFormat.PlainText)
        details_layout.addWidget(destination_label)

        destination = QLabel(_display_path(screen_ai_install_dir()))
        destination.setObjectName("pathText")
        destination.setTextFormat(Qt.TextFormat.PlainText)
        destination.setWordWrap(True)
        destination.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(destination)

        size_label = QLabel(f"Approx. installed size: {APPROX_INSTALLED_SIZE}.")
        size_label.setObjectName("detailText")
        size_label.setTextFormat(Qt.TextFormat.PlainText)
        details_layout.addWidget(size_label)
        main_layout.addWidget(details_panel)

        if installed:
            replace_note = QLabel("The existing component files will be replaced. Restart MeikiKai before OCR resumes.")
            replace_note.setObjectName("detailText")
            replace_note.setTextFormat(Qt.TextFormat.PlainText)
            replace_note.setWordWrap(True)
            replace_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            main_layout.addWidget(replace_note)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumWidth(78)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        primary_button = QPushButton("Reinstall/update" if installed else "Download")
        primary_button.setObjectName("primaryButton")
        primary_button.setMinimumWidth(116 if installed else 92)
        primary_button.clicked.connect(self.accept)
        primary_button.setDefault(True)
        button_layout.addWidget(primary_button)
        main_layout.addLayout(button_layout)

        self.setFixedHeight(self.sizeHint().height())

    def _bullet_row(self, text: str):
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        marker = QLabel("•")
        marker.setObjectName("bulletMarker")
        marker.setTextFormat(Qt.TextFormat.PlainText)
        marker.setFixedWidth(10)
        row_layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignTop)

        label = QLabel(text)
        label.setObjectName("confirmBody")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_layout.addWidget(label, 1)
        return row

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
            QLabel#confirmBody {{
                color: {MUTED_COLOR};
                font-size: 12px;
                line-height: 145%;
            }}
            QLabel#bulletMarker {{
                color: #6f90bd;
                font-size: 14px;
                font-weight: 800;
            }}
            QFrame#detailsPanel {{
                background-color: rgba(237, 241, 247, 10);
                border: 1px solid rgba(237, 241, 247, 24);
                border-radius: 10px;
            }}
            QLabel#detailTitle {{
                color: {TEXT_COLOR};
                font-size: 11px;
                font-weight: 750;
            }}
            QLabel#detailText {{
                color: {SUBTLE_COLOR};
                font-size: 11px;
            }}
            QLabel#pathText {{
                color: {MUTED_COLOR};
                font-family: "SF Mono", Menlo, Monaco, monospace;
                font-size: 11px;
            }}
            QPushButton {{
                background-color: rgba(237, 241, 247, 14);
                border: 1px solid rgba(237, 241, 247, 42);
                border-radius: 7px;
                color: {TEXT_COLOR};
                font-weight: 650;
                min-height: 24px;
                padding: 3px 10px;
            }}
            QPushButton:hover {{
                background-color: rgba(237, 241, 247, 24);
                border-color: rgba(237, 241, 247, 70);
            }}
            QPushButton:pressed {{
                background-color: rgba(237, 241, 247, 32);
            }}
            QPushButton#primaryButton {{
                background-color: #0a84ff;
                border-color: rgba(123, 193, 255, 170);
                color: #ffffff;
            }}
            QPushButton#primaryButton:hover {{
                background-color: #2492ff;
            }}
            QPushButton#primaryButton:disabled {{
                background-color: rgba(237, 241, 247, 8);
                border-color: rgba(237, 241, 247, 18);
                color: rgba(237, 241, 247, 84);
            }}
        """)


class ScreenAiUninstallConfirmDialog(QDialog):
    def __init__(self, status: ScreenAiComponentStatus, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Uninstall Chrome Screen AI?")
        self.setWindowIcon(QIcon(paths.get_resource_path('app_icon.icns')))
        self.setFixedWidth(500)
        self._apply_window_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 20, 18, 16)
        main_layout.setSpacing(12)

        title = QLabel("Uninstall Chrome Screen AI?")
        title.setObjectName("dialogTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title.setFixedHeight(DIALOG_TITLE_HEIGHT)
        main_layout.addWidget(title)

        body = QLabel(
            "Remove the local Chrome Screen AI files installed for MeikiKai. OCR will be disabled until you download it again."
        )
        body.setObjectName("confirmBody")
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setWordWrap(True)
        main_layout.addWidget(body)

        details_panel = QFrame()
        details_panel.setObjectName("detailsPanel")
        details_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        details_layout = QVBoxLayout(details_panel)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_layout.setSpacing(4)

        location_label = QLabel("Remove location")
        location_label.setObjectName("detailTitle")
        location_label.setTextFormat(Qt.TextFormat.PlainText)
        details_layout.addWidget(location_label)

        location = QLabel(_display_path(status.install_dir))
        location.setObjectName("pathText")
        location.setTextFormat(Qt.TextFormat.PlainText)
        location.setWordWrap(True)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(location)
        main_layout.addWidget(details_panel)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumWidth(78)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        uninstall_button = QPushButton("Uninstall")
        uninstall_button.setObjectName("destructiveButton")
        uninstall_button.setMinimumWidth(86)
        uninstall_button.clicked.connect(self.accept)
        button_layout.addWidget(uninstall_button)
        main_layout.addLayout(button_layout)

        self.setFixedHeight(self.sizeHint().height())

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
            QLabel#confirmBody {{
                color: {MUTED_COLOR};
                font-size: 12px;
                line-height: 145%;
            }}
            QFrame#detailsPanel {{
                background-color: rgba(237, 241, 247, 10);
                border: 1px solid rgba(237, 241, 247, 24);
                border-radius: 10px;
            }}
            QLabel#detailTitle {{
                color: {TEXT_COLOR};
                font-size: 11px;
                font-weight: 750;
            }}
            QLabel#pathText {{
                color: {MUTED_COLOR};
                font-family: "SF Mono", Menlo, Monaco, monospace;
                font-size: 11px;
            }}
            QPushButton {{
                background-color: rgba(237, 241, 247, 14);
                border: 1px solid rgba(237, 241, 247, 42);
                border-radius: 7px;
                color: {TEXT_COLOR};
                font-weight: 650;
                min-height: 24px;
                padding: 3px 10px;
            }}
            QPushButton:hover {{
                background-color: rgba(237, 241, 247, 24);
                border-color: rgba(237, 241, 247, 70);
            }}
            QPushButton#destructiveButton {{
                background-color: rgba(255, 69, 58, 16);
                border-color: rgba(255, 105, 97, 95);
                color: #ffd7d4;
            }}
            QPushButton#destructiveButton:hover {{
                background-color: rgba(255, 69, 58, 30);
                border-color: rgba(255, 105, 97, 135);
                color: #ffffff;
            }}
        """)


class ScreenAiMessageDialog(QDialog):
    def __init__(self, title: str, message: str, detail: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(paths.get_resource_path('app_icon.icns')))
        self.setFixedWidth(500)
        self._apply_window_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 20, 18, 16)
        main_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("dialogTitle")
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        title_label.setWordWrap(True)
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title_label.setFixedHeight(DIALOG_TITLE_HEIGHT)
        main_layout.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setObjectName("messageBody")
        message_label.setTextFormat(Qt.TextFormat.PlainText)
        message_label.setWordWrap(True)
        main_layout.addWidget(message_label)

        if detail:
            detail_panel = QFrame()
            detail_panel.setObjectName("detailsPanel")
            detail_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            detail_layout = QVBoxLayout(detail_panel)
            detail_layout.setContentsMargins(12, 10, 12, 10)
            detail_layout.setSpacing(0)
            detail_label = QLabel(detail)
            detail_label.setObjectName("messageDetail")
            detail_label.setTextFormat(Qt.TextFormat.PlainText)
            detail_label.setWordWrap(True)
            detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_layout.addWidget(detail_label)
            main_layout.addWidget(detail_panel)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        ok_button = QPushButton("OK")
        ok_button.setObjectName("primaryButton")
        ok_button.setMinimumWidth(76)
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)
        main_layout.addLayout(button_layout)

        self.setFixedHeight(self.sizeHint().height())

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
            QLabel#messageBody {{
                color: {MUTED_COLOR};
                font-size: 12px;
                line-height: 145%;
            }}
            QFrame#detailsPanel {{
                background-color: rgba(237, 241, 247, 10);
                border: 1px solid rgba(237, 241, 247, 24);
                border-radius: 10px;
            }}
            QLabel#messageDetail {{
                color: {MUTED_COLOR};
                font-family: "SF Mono", Menlo, Monaco, monospace;
                font-size: 11px;
            }}
            QPushButton {{
                background-color: rgba(237, 241, 247, 14);
                border: 1px solid rgba(237, 241, 247, 42);
                border-radius: 7px;
                color: {TEXT_COLOR};
                font-weight: 650;
                min-height: 24px;
                padding: 3px 10px;
            }}
            QPushButton:hover {{
                background-color: rgba(237, 241, 247, 24);
                border-color: rgba(237, 241, 247, 70);
            }}
            QPushButton#primaryButton {{
                background-color: #0a84ff;
                border-color: rgba(123, 193, 255, 170);
                color: #ffffff;
            }}
            QPushButton#primaryButton:hover {{
                background-color: #2492ff;
            }}
        """)


class ScreenAiSetupDialog(QDialog):
    def __init__(self, ocr_processor=None, tray_icon=None, setup_required: bool = False, parent=None):
        super().__init__(parent)
        self.ocr_processor = ocr_processor
        self.tray_icon = tray_icon
        self.setup_required = setup_required
        self._worker_thread: QThread | None = None
        self._worker: ScreenAiInstallWorker | None = None
        self._status_labels: dict[str, QLabel] = {}
        self.title_label: QLabel | None = None
        self.quit_button: QPushButton | None = None
        self.close_button: QPushButton | None = None
        self._restore_backend_on_error = False

        self.setWindowTitle("MeikiKai Setup" if setup_required else "Chrome Screen AI Setup")
        self.setWindowIcon(QIcon(paths.get_resource_path('app_icon.icns')))
        self.setFixedWidth(600)
        self._apply_window_style()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 20, 18, 20)
        main_layout.setSpacing(12)

        self.title_label = QLabel("OCR engine required")
        self.title_label.setObjectName("dialogTitle")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.title_label.setFixedHeight(DIALOG_TITLE_HEIGHT)
        main_layout.addWidget(self.title_label)

        disclosure = QLabel(
            "MeikiKai uses Chrome Screen AI to read Japanese text from your screen.\n\n"
            "Downloaded on demand from Google/Chromium public infrastructure. Not bundled with or made by "
            "MeikiKai, and MeikiKai is not affiliated with Google or Chromium. Experimental for this use "
            "and removable at any time."
        )
        disclosure.setObjectName("bodyText")
        disclosure.setWordWrap(True)
        disclosure.setTextFormat(Qt.TextFormat.PlainText)
        main_layout.addWidget(disclosure)

        main_layout.addWidget(self._status_panel())

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("progressText")
        self.progress_label.setTextFormat(Qt.TextFormat.PlainText)
        self.progress_label.setWordWrap(True)
        self.progress_label.setVisible(False)
        main_layout.addWidget(self.progress_label)

        self.download_button = QPushButton("Download Chrome Screen AI")
        self.download_button.setObjectName("primaryButton")
        self.download_button.setMinimumWidth(190)
        self.download_button.clicked.connect(self.confirm_download)

        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(8)
        primary_actions.addWidget(self.download_button)
        primary_actions.addStretch(1)
        main_layout.addLayout(primary_actions)

        self.notices_button = QPushButton("Open third-party notices")
        self.notices_button.setMinimumWidth(158)
        self.notices_button.clicked.connect(self.open_notices)
        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.setObjectName("destructiveButton")
        self.uninstall_button.setMinimumWidth(82)
        self.uninstall_button.clicked.connect(self.confirm_uninstall)

        self.maintenance_widget = QWidget()
        maintenance_actions = QHBoxLayout(self.maintenance_widget)
        maintenance_actions.setContentsMargins(0, 0, 0, 0)
        maintenance_actions.setSpacing(8)
        maintenance_actions.addWidget(self.notices_button)
        maintenance_actions.addWidget(self.uninstall_button)
        maintenance_actions.addStretch(1)
        main_layout.addWidget(self.maintenance_widget)

        separator = QFrame()
        separator.setObjectName("rowSeparator")
        separator.setFixedHeight(1)
        main_layout.addSpacing(2)
        main_layout.addWidget(separator)

        bottom_actions = QHBoxLayout()
        bottom_actions.addStretch(1)
        if setup_required:
            self.quit_button = QPushButton(f"Quit {APP_NAME}")
            self.quit_button.setObjectName("destructiveButton")
            self.quit_button.setMinimumWidth(108)
            self.quit_button.clicked.connect(QApplication.instance().quit)
            bottom_actions.addWidget(self.quit_button)
        self.close_button = QPushButton("Not Now" if setup_required else "Close")
        self.close_button.setMinimumWidth(78)
        self.close_button.clicked.connect(self.accept)
        bottom_actions.addWidget(self.close_button)
        main_layout.addLayout(bottom_actions)

        self.refresh_status()
        self.setFixedHeight(self.sizeHint().height())

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
            QLabel#bodyText {{
                color: {MUTED_COLOR};
                font-size: 12px;
                line-height: 145%;
            }}
            QLabel#progressText {{
                background-color: rgba(10, 132, 255, 14);
                border: 1px solid rgba(10, 132, 255, 48);
                border-radius: 10px;
                color: #c8e1ff;
                font-size: 12px;
                font-weight: 650;
                line-height: 145%;
                padding: 8px 10px;
            }}
            QLabel#statusTitle {{
                color: {SUBTLE_COLOR};
                font-size: 11px;
                font-weight: 700;
            }}
            QLabel#statusValue {{
                color: #cdd4e2;
                font-size: 12px;
                font-weight: 600;
            }}
            QFrame#statusPanel {{
                background-color: {PANEL_BG};
                border: 1px solid {PANEL_BORDER};
                border-radius: 14px;
            }}
            QFrame#rowSeparator {{
                background-color: rgba(237, 241, 247, 18);
                border: none;
            }}
            QPushButton {{
                background-color: rgba(237, 241, 247, 14);
                border: 1px solid rgba(237, 241, 247, 42);
                border-radius: 7px;
                color: {TEXT_COLOR};
                font-weight: 650;
                min-height: 24px;
                padding: 3px 10px;
            }}
            QPushButton:hover {{
                background-color: rgba(237, 241, 247, 24);
                border-color: rgba(237, 241, 247, 70);
            }}
            QPushButton:pressed {{
                background-color: rgba(237, 241, 247, 32);
            }}
            QPushButton:disabled {{
                background-color: rgba(237, 241, 247, 8);
                border-color: rgba(237, 241, 247, 18);
                color: rgba(237, 241, 247, 84);
            }}
            QPushButton#primaryButton {{
                background-color: #0a84ff;
                border-color: rgba(123, 193, 255, 170);
                color: #ffffff;
            }}
            QPushButton#primaryButton:hover {{
                background-color: #2492ff;
            }}
            QPushButton#primaryButton:pressed {{
                background-color: #006edb;
            }}
            QPushButton#primaryButton:disabled {{
                background-color: rgba(237, 241, 247, 8);
                border-color: rgba(237, 241, 247, 18);
                color: rgba(237, 241, 247, 84);
            }}
            QPushButton#destructiveButton {{
                background-color: rgba(255, 69, 58, 12);
                border-color: rgba(255, 105, 97, 70);
                color: #ffd7d4;
            }}
            QPushButton#destructiveButton:hover {{
                background-color: rgba(255, 69, 58, 28);
                border-color: rgba(255, 105, 97, 120);
                color: #ffffff;
            }}
            QPushButton#destructiveButton:disabled {{
                background-color: rgba(237, 241, 247, 8);
                border-color: rgba(237, 241, 247, 18);
                color: rgba(237, 241, 247, 84);
            }}
        """)

    def _status_panel(self):
        panel = QFrame()
        panel.setObjectName("statusPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        grid = QGridLayout(panel)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)

        for row, (key, title) in enumerate((
            ("status", "Status"),
            ("source", "Source"),
            ("version", "Version"),
            ("package", "Package"),
            ("location", "Location"),
        )):
            title_label = QLabel(title)
            title_label.setObjectName("statusTitle")
            title_label.setTextFormat(Qt.TextFormat.PlainText)
            title_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            value_label = QLabel("-")
            value_label.setObjectName("statusValue")
            value_label.setTextFormat(Qt.TextFormat.PlainText)
            value_label.setWordWrap(True)
            value_label.setMinimumWidth(0)
            value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            self._status_labels[key] = value_label
            grid.addWidget(title_label, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_label, row, 1)

        return panel

    def refresh_status(self):
        status = get_screen_ai_status()
        ready = bool(self.ocr_processor and self.ocr_processor.is_backend_available())
        if ready:
            status_text = "Installed and ready"
            title_text = "OCR engine ready"
        elif status.installed:
            last_error = getattr(self.ocr_processor, "last_error", None)
            status_text = "Installed, but OCR is not loaded"
            title_text = "OCR engine installed"
            if last_error:
                status_text = f"{status_text}: {last_error}"
        else:
            status_text = "Not installed"
            title_text = "OCR engine required"

        if self.title_label:
            self.title_label.setText(title_text)
        self._status_labels["status"].setText(status_text)
        self._status_labels["source"].setText(status.source if status.installed else CIPD_SOURCE_LABEL)
        self._status_labels["version"].setText(status.version_display if status.installed else "—")
        self._status_labels["package"].setText(status.package or "Unknown")
        self._status_labels["location"].setText(_display_path(status.location_display))

        self.download_button.setText("Reinstall/update Chrome Screen AI" if status.installed else "Download Chrome Screen AI")
        self._set_primary_button(self.download_button, not status.installed)
        if self.close_button:
            self.close_button.setText("Close" if ready or not self.setup_required else "Not Now")
        self.maintenance_widget.setVisible(status.installed)
        self.uninstall_button.setEnabled(status.installed)
        self.notices_button.setEnabled(status.installed)
        self.setFixedHeight(self.sizeHint().height())

    def confirm_download(self):
        status = get_screen_ai_status()
        confirmation = ScreenAiDownloadConfirmDialog(status.installed, self)
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_worker()

    def open_notices(self):
        status = get_screen_ai_status()
        notice_path = status.notices_path or status.readme_path
        if not notice_path:
            ScreenAiMessageDialog(
                "Third-party notices unavailable",
                "No THIRD_PARTY_LICENSES or README.md file was found in the installed Chrome Screen AI component.",
                parent=self,
            ).exec()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(notice_path)))

    def confirm_uninstall(self):
        status = get_screen_ai_status()
        if not status.installed:
            self.refresh_status()
            return

        if ScreenAiUninstallConfirmDialog(status, self).exec() != QDialog.DialogCode.Accepted:
            return

        try:
            if self.ocr_processor:
                self.ocr_processor.unload_ocr_backend("Chrome Screen AI was uninstalled.")
            uninstall_screen_ai()
        except Exception as e:
            ScreenAiMessageDialog(
                "Uninstall failed",
                "MeikiKai could not remove the Chrome Screen AI files.",
                str(e),
                parent=self,
            ).exec()
            return

        self._set_progress("Chrome Screen AI was removed. OCR is disabled until setup succeeds.")
        self.refresh_status()
        self._notify_tray_status()

    def _start_worker(self):
        if self._worker_thread and self._worker_thread.isRunning():
            return

        self._restore_backend_on_error = bool(self.ocr_processor and self.ocr_processor.is_backend_available())
        if self._restore_backend_on_error:
            self.ocr_processor.unload_ocr_backend("Restart MeikiKai to use the updated Chrome Screen AI.")
            self._notify_tray_status()

        self._set_busy(True)
        self._set_progress("Starting Chrome Screen AI setup…")
        self._worker_thread = QThread(self)
        self._worker = ScreenAiInstallWorker()
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._set_progress)
        self._worker.finished.connect(self._handle_install_finished)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.finished.connect(self._clear_worker)
        self._worker_thread.start()

    @pyqtSlot(object, object)
    def _handle_install_finished(self, status: ScreenAiComponentStatus | None, error: str | None):
        self._set_busy(False)
        if error:
            self._restore_backend_on_error = False
            self._set_progress("Chrome Screen AI setup failed. Restart MeikiKai if OCR was already running.")
            ScreenAiMessageDialog(
                "Chrome Screen AI setup failed",
                "MeikiKai could not download or install Chrome Screen AI.",
                error,
                parent=self,
            ).exec()
            self.refresh_status()
            self._notify_tray_status()
            return

        if self._restore_backend_on_error:
            self._restore_backend_on_error = False
            if self.ocr_processor:
                self.ocr_processor.unload_ocr_backend("Restart MeikiKai to use the updated Chrome Screen AI.")
            self._set_progress("Chrome Screen AI updated. Restart MeikiKai to use the updated OCR engine.")
            ScreenAiMessageDialog(
                "Restart MeikiKai to finish updating OCR",
                "Chrome Screen AI was updated, but native OCR components cannot be safely reloaded while MeikiKai is running.",
                "Quit and reopen MeikiKai to use the updated OCR engine.",
                parent=self,
            ).exec()
            self.refresh_status()
            self._notify_tray_status()
            return

        self._set_progress("Chrome Screen AI installed. Initializing OCR engine…")
        if self.ocr_processor and not self.ocr_processor.reload_ocr_backend():
            error_text = self.ocr_processor.last_error or "Unknown OCR initialization error."
            ScreenAiMessageDialog(
                "OCR initialization failed",
                "Chrome Screen AI was installed, but MeikiKai could not initialize OCR.",
                error_text,
                parent=self,
            ).exec()
        else:
            self._set_progress("Chrome Screen AI is installed and OCR is ready.")

        self.refresh_status()
        self._notify_tray_status()

    def _clear_worker(self):
        self._worker_thread = None
        self._worker = None

    @pyqtSlot(str)
    def _set_progress(self, message: str):
        self.progress_label.setText(message)
        self.progress_label.setVisible(bool(message))
        self.setFixedHeight(self.sizeHint().height())

    def _set_primary_button(self, button: QPushButton, primary: bool):
        button.setObjectName("primaryButton" if primary else "")
        button.style().unpolish(button)
        button.style().polish(button)

    def _set_busy(self, busy: bool):
        for button in (
            self.download_button,
            self.notices_button,
            self.uninstall_button,
            self.close_button,
            self.quit_button,
        ):
            if button:
                button.setEnabled(not busy)

    def _notify_tray_status(self):
        if self.tray_icon and hasattr(self.tray_icon, "reapply_settings"):
            self.tray_icon.reapply_settings()

    def accept(self):
        if self._worker_thread and self._worker_thread.isRunning():
            return
        super().accept()

    def reject(self):
        if self._worker_thread and self._worker_thread.isRunning():
            return
        super().reject()
