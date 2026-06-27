# meikikai/main.py
import argparse
import signal
import sys
import threading
import webbrowser
from urllib.parse import quote

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from meikikai.utils.logger import setup_logging
from meikikai.anki.cards import DECK_NAME, MODEL_NAME
from meikikai.anki.screenshot import capture_interactive_png
from meikikai.anki.worker import AnkiExportNotifier, AnkiExportWorker
from meikikai.config.config import APP_NAME, APP_VERSION, config
from meikikai.dictionary.lookup import Lookup
from meikikai.gui.input import GlobalHotkeyListener, InputLoop, request_accessibility_access
from meikikai.gui.popup import Popup
from meikikai.gui.tray import TrayIcon
from meikikai.ocr.hit_scan import HitScanner
from meikikai.ocr.ocr import OcrProcessor
from meikikai.screenshot.screenmanager import ScreenManager
from meikikai.tts.worker import SpeechPlaybackNotifier, ShortcutsSpeechWorker
from meikikai.utils.capture_state import begin_capture_interaction, end_capture_interaction
from meikikai.utils.latest_queue import LatestValueQueue
from meikikai.utils.paths import paths


def set_app_icon(app):
    icon_path = paths.get_resource_path('app_icon.icns')
    app.setWindowIcon(QIcon(icon_path))

    try:
        from AppKit import NSApplication, NSImage

        image = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if image is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception:
        pass


def request_screen_recording_access():
    """Ask macOS to validate Screen Recording access for this exact app bundle."""
    try:
        import Quartz

        if hasattr(Quartz, 'CGPreflightScreenCaptureAccess') and Quartz.CGPreflightScreenCaptureAccess():
            return
        if hasattr(Quartz, 'CGRequestScreenCaptureAccess'):
            Quartz.CGRequestScreenCaptureAccess()
    except Exception:
        pass


def request_input_access():
    """Ask macOS to validate Accessibility access for input handling."""
    try:
        request_accessibility_access()
    except Exception:
        pass


def set_activation_policy_accessory():
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception:
        pass


class SharedState:
    def __init__(self):
        self.running = True

        # events and queues
        self.screenshot_trigger_event = threading.Event()
        self.ocr_available_event = threading.Event()
        self.ocr_queue = LatestValueQueue()
        self.hit_scan_queue = LatestValueQueue()
        self.lookup_queue = LatestValueQueue()

        # screen lock - used by screen manager and popup
        self.screen_lock = threading.RLock()


class ClipboardController(QObject):
    copy_requested = pyqtSignal(str)
    message = pyqtSignal(str, str, str)

    def __init__(self):
        super().__init__()
        self.copy_requested.connect(self._copy_to_clipboard)

    @pyqtSlot(str)
    def _copy_to_clipboard(self, text: str):
        QApplication.clipboard().setText(text)
        self.message.emit("Copied to clipboard", f"Copied {text}.", "success")


class JishoSearchController(QObject):
    search_requested = pyqtSignal(str)
    message = pyqtSignal(str, str, str)

    def __init__(self, popup_window: Popup):
        super().__init__()
        self.popup_window = popup_window
        self.search_requested.connect(self._open_search)

    @pyqtSlot(str)
    def _open_search(self, query: str):
        query = query.strip()
        if not query:
            self.message.emit(
                "Jisho search skipped",
                "No visible vocabulary entry to search.",
                "warning",
            )
            return

        url = f"https://jisho.org/search/{quote(query, safe='')}"
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False

        if not opened:
            self.message.emit(
                "Jisho search failed",
                "Could not open Jisho.org in the default browser.",
                "critical",
            )
            return

        self.popup_window.hide_popup_for_external_navigation()


def run_gui():
    setup_logging()
    shared_state = SharedState()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    set_app_icon(app)
    set_activation_policy_accessory()
    request_screen_recording_access()
    request_input_access()

    input_loop = InputLoop(shared_state)
    popup_window = Popup(shared_state)

    screen_manager = ScreenManager(shared_state)
    lookup = Lookup(shared_state, popup_window)  # load dictionary

    ocr_processor = OcrProcessor(shared_state)
    hit_scanner = HitScanner(shared_state, input_loop, screen_manager)
    tray_icon = TrayIcon(screen_manager, popup_window, ocr_processor)

    anki_notifier = AnkiExportNotifier()
    anki_notifier.message.connect(tray_icon.show_anki_message)
    clipboard_controller = ClipboardController()
    clipboard_controller.message.connect(tray_icon.show_status_message)
    jisho_controller = JishoSearchController(popup_window)
    jisho_controller.message.connect(tray_icon.show_status_message)
    speech_notifier = SpeechPlaybackNotifier()
    speech_notifier.message.connect(tray_icon.show_status_message)
    speech_worker = ShortcutsSpeechWorker(speech_notifier)
    anki_worker = AnkiExportWorker(
        config.anki_connect_url,
        DECK_NAME,
        MODEL_NAME,
        anki_notifier,
    )

    anki_capture_lock = threading.Lock()

    def export_latest_to_anki():
        export_data = popup_window.get_latest_export_data()
        if export_data is None:
            return False

        if not config.anki_capture_screenshot:
            anki_worker.submit(export_data)
            return True

        if not anki_capture_lock.acquire(blocking=False):
            anki_notifier.message.emit(
                "Screenshot capture active",
                "Finish or cancel the current crop before creating another Anki card.",
                "warning",
            )
            return True

        begin_capture_interaction()

        def capture_and_submit():
            try:
                screenshot_path = capture_interactive_png()
                if screenshot_path is None:
                    anki_notifier.message.emit(
                        "Anki export canceled",
                        "Screenshot capture canceled; no card was created.",
                        "info",
                    )
                    return

                anki_worker.submit(export_data, screenshot_path)
            finally:
                end_capture_interaction()
                anki_capture_lock.release()

        capture_thread = threading.Thread(target=capture_and_submit, daemon=True, name="AnkiScreenshotCapture")
        try:
            capture_thread.start()
        except Exception:
            end_capture_interaction()
            anki_capture_lock.release()
            raise
        return True

    def copy_latest_to_clipboard():
        if not popup_window.is_visible or config.is_paused:
            return False

        text = popup_window.get_latest_copy_text()
        if not text:
            clipboard_controller.message.emit(
                "Clipboard copy skipped",
                "No visible vocabulary entry to copy.",
                "warning",
            )
            return True

        clipboard_controller.copy_requested.emit(text)
        return True

    def search_latest_on_jisho():
        if not popup_window.is_visible or config.is_paused:
            return False

        query = popup_window.get_latest_jisho_query()
        if not query:
            jisho_controller.message.emit(
                "Jisho search skipped",
                "No visible vocabulary entry to search.",
                "warning",
            )
            return True

        jisho_controller.search_requested.emit(query)
        return True

    def speak_latest_entry():
        if not popup_window.is_visible or config.is_paused:
            return False

        text = popup_window.get_latest_speech_text()
        if not text:
            speech_notifier.message.emit(
                "Speech skipped",
                "No visible vocabulary entry to speak.",
                "warning",
            )
            return True

        if not config.shortcuts_tts_enabled:
            speech_notifier.message.emit(
                "Speech disabled",
                "Enable Shortcuts TTS in Settings → Speech, then Save.",
                "warning",
            )
            return True

        if not speech_worker.submit(text):
            speech_notifier.message.emit(
                "Speech already running",
                "Wait for the current speech request to finish.",
                "warning",
            )
        return True

    global_hotkeys = GlobalHotkeyListener(
        export_latest_to_anki,
        copy_latest_to_clipboard,
        search_latest_on_jisho,
        speak_latest_entry,
    )

    for t in [lookup, hit_scanner, ocr_processor, screen_manager, input_loop, anki_worker, speech_worker]:
        t.start()
    global_hotkeys.start()

    if not ocr_processor.is_backend_available():
        QTimer.singleShot(250, tray_icon.show_screen_ai_setup)

    ready_message = f"""
    --------------------------------------------------
    {APP_NAME}.{APP_VERSION} is running in the background.

      - To configure or change scan screen: Right-click the menu bar icon.
      - While the popup is visible, press C to copy the top entry expression.
      - While the popup is visible, press J to search the top entry on Jisho.org.
      - While the popup is visible, press S to speak the top entry reading or expression.
      - While the popup is visible, press A to export the top entry to Anki.
      - To exit: Press Ctrl+C in this terminal.

    --------------------------------------------------
    """
    print(ready_message)

    def signal_handler(sig, frame):
        QApplication.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    exit_code = app.exec()

    global_hotkeys.stop()
    anki_worker.stop()
    speech_worker.stop()
    shared_state.running = False
    shared_state.screenshot_trigger_event.set()
    shared_state.ocr_queue.put(None)
    shared_state.hit_scan_queue.trigger()
    shared_state.lookup_queue.put(None)
    sys.exit(exit_code)


def main():
    parser = argparse.ArgumentParser(
        prog="meikikai",
        description="Japanese OCR popup dictionary for macOS"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("build-dict", help="Build the dictionary from source files")

    import_html_parser = subparsers.add_parser("import-yomitan-dict-html", help="Import Yomitan dictionary (HTML format)")
    import_html_parser.add_argument("dictionary_files", nargs='+', help="Path(s) to the dictionary zip file(s)")

    import_text_parser = subparsers.add_parser("import-yomitan-dict-text", help="Import Yomitan dictionary (text format)")
    import_text_parser.add_argument("dictionary_files", nargs='+', help="Path(s) to the dictionary zip file(s)")

    args = parser.parse_args()

    if args.command == "build-dict":
        from meikikai.scripts.build_dictionary import main as build_main
        build_main()
    elif args.command == "import-yomitan-dict-html":
        from meikikai.scripts.import_yomitan_dict_html import main as import_html_main
        import_html_main([*args.dictionary_files])
    elif args.command == "import-yomitan-dict-text":
        from meikikai.scripts.import_yomitan_dict_text import main as import_text_main
        import_text_main([*args.dictionary_files])
    else:
        run_gui()


if __name__ == "__main__":
    main()
