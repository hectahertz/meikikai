# meikikai/gui/tray.py
import os

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon, QAction, QActionGroup
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from meikikai.config.config import APP_NAME, config
from meikikai.gui.settings_dialog import SettingsDialog
from meikikai.ocr.ocr import OcrProcessor
from meikikai.utils.paths import paths

class TrayIcon(QSystemTrayIcon):
    def __init__(self, screen_manager, ocr_processor: OcrProcessor, popup_window, parent=None):
        icon_path = paths.get_resource_path('menubar_icon.png')
        icon_inactive_path = paths.get_resource_path('menubar_icon.inactive.png')

        if os.path.exists(icon_path) and os.path.exists(icon_inactive_path):
            self.icon = QIcon(icon_path)
            self.icon_inactive = QIcon(icon_inactive_path)
            self.icon.setIsMask(True)
            self.icon_inactive.setIsMask(True)
        else:
            from PyQt6.QtWidgets import QStyle
            self.icon = QIcon(QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            ))
            self.icon_inactive = self.icon
        super().__init__(self.icon, parent)

        self.screen_manager = screen_manager
        self.ocr_processor = ocr_processor
        self.popup_window = popup_window
        self.scan_screen_actions = []

        self.menu = QMenu()

        self.pause_action = self.menu.addAction(f"Pause {APP_NAME}")
        self.pause_action.setCheckable(True)
        self.pause_action.triggered.connect(self.set_paused_state)
        self.set_paused_state(config.is_paused)

        self.auto_pause_media_action = self.menu.addAction("Auto Pause Media")
        self.auto_pause_media_action.setCheckable(True)
        self.auto_pause_media_action.setToolTip(
            "Pause media when the popup opens, then resume only if media was playing before."
        )
        self.auto_pause_media_action.setChecked(config.auto_pause_media)
        self.auto_pause_media_action.triggered.connect(self.set_auto_pause_media_state)

        self.menu.addSeparator()

        self.menu.addAction("Settings").triggered.connect(self.show_settings)

        self.menu.addSeparator()

        # Scan Screen Selection
        scan_screen_menu = self.menu.addMenu("Scan Screen")
        self.scan_screen_action_group = QActionGroup(self)
        self.scan_screen_action_group.setExclusive(True)
        self.scan_screen_action_group.triggered.connect(self._on_scan_screen_selected)

        for i, res in enumerate(self.screen_manager.get_screens()):
            label = "All Screens" if i == 0 else f"Screen {i}"
            action = scan_screen_menu.addAction(f"{label} ({res['width']}x{res['height']})")
            action.setCheckable(True)
            action.setData(i)
            self.scan_screen_action_group.addAction(action)
            self.scan_screen_actions.append(action)

        self.update_scan_screen_check()

        self.menu.addSeparator()

        self.menu.addAction("Quit").triggered.connect(QApplication.instance().quit)

        self.setContextMenu(self.menu)
        self.setToolTip(APP_NAME)
        self.show()

    def set_paused_state(self, paused):
        """Sets the paused state of the application."""
        config.is_paused = paused
        self.pause_action.setChecked(paused)
        if paused:
            self.setIcon(self.icon_inactive)
        else:
            self.setIcon(self.icon)

    def set_auto_pause_media_state(self, enabled):
        config.auto_pause_media = enabled
        self.auto_pause_media_action.setChecked(enabled)
        config.save()

    def update_scan_screen_check(self):
        current_screen = config.scan_screen
        action_to_check = None
        for action in self.scan_screen_actions:
            if action.data() == current_screen:
                action_to_check = action
                break

        if not action_to_check:
            action_to_check = self.scan_screen_actions[0]

        action_to_check.setChecked(True)

    def _on_scan_screen_selected(self, action: QAction):
        index = int(action.data())
        if index != config.scan_screen:
            if self.screen_manager.set_scan_screen(index):
                config.scan_screen = index
                config.save()
            else:
                self.update_scan_screen_check()

    def reapply_settings(self):
        """Updates the tray menu's checkmarks to reflect the current config."""
        self.auto_pause_media_action.setChecked(config.auto_pause_media)

    def show_anki_message(self, title: str, message: str, level: str = "info"):
        icons = {
            "success": QSystemTrayIcon.MessageIcon.Information,
            "duplicate": QSystemTrayIcon.MessageIcon.Information,
            "info": QSystemTrayIcon.MessageIcon.Information,
            "warning": QSystemTrayIcon.MessageIcon.Warning,
            "critical": QSystemTrayIcon.MessageIcon.Critical,
        }
        self.showMessage(title, message, icons.get(level, QSystemTrayIcon.MessageIcon.Information), 4500)

    def show_settings(self):
        settings_dialog = SettingsDialog(self.ocr_processor, self.popup_window, self)
        self._activate_app_on_mac()
        QTimer.singleShot(0, lambda: self._raise_settings_dialog(settings_dialog))
        settings_dialog.exec()

    def _raise_settings_dialog(self, settings_dialog):
        settings_dialog.raise_()
        settings_dialog.activateWindow()

    def _activate_app_on_mac(self):
        try:
            from AppKit import NSApplication

            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass
