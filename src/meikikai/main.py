# meikikai/main.py
import argparse
import signal
import sys
import threading

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from meikikai.utils.logger import setup_logging
from meikikai.config.config import config, APP_NAME, APP_VERSION
from meikikai.dictionary.lookup import Lookup
from meikikai.gui.input import InputLoop, request_accessibility_access
from meikikai.gui.popup import Popup
from meikikai.gui.tray import TrayIcon
from meikikai.ocr.hit_scan import HitScanner
from meikikai.ocr.ocr import OcrProcessor
from meikikai.screenshot.screenmanager import ScreenManager
from meikikai.utils.lastest_queue import LatestValueQueue
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
    """Ask macOS to validate Accessibility access for media key automation."""
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
        self.ocr_queue = LatestValueQueue()
        self.hit_scan_queue = LatestValueQueue()
        self.lookup_queue = LatestValueQueue()

        # screen lock - used by screen manager and popup
        self.screen_lock = threading.RLock()


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
    tray_icon = TrayIcon(screen_manager, ocr_processor, popup_window)

    for t in [lookup, hit_scanner, ocr_processor, screen_manager, input_loop]:
        t.start()

    ready_message = f"""
    --------------------------------------------------
    {APP_NAME}.{APP_VERSION} is running in the background.

      - To configure or change scan screen: Right-click the menu bar icon.
      - To exit: Press Ctrl+C in this terminal.

    --------------------------------------------------
    """
    print(ready_message)

    def signal_handler(sig, frame):
        QApplication.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    exit_code = app.exec()

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
