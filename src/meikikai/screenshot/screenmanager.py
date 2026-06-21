# meikikai/screenshot/screenmanager.py
import logging
import threading
import time

import mss
from PIL import Image

from meikikai.config.config import config

logger = logging.getLogger(__name__)


# todo doesnt work when monitors change
class ScreenManager(threading.Thread):
    def __init__(self, shared_state, input_loop):
        super().__init__(daemon=True, name="ScreenManager")
        self.shared_state = shared_state
        self.monitor = None
        self.last_ocr_put_time = 0.0
        self.last_screenshot = None
        self.last_mouse_pos = None
        self.input_loop = input_loop
        try:
            screen_idx = int(config.scan_screen)
        except (TypeError, ValueError):
            logger.warning(f"Invalid screen '{config.scan_screen}' in config, defaulting to screen 1.")
            screen_idx = 1

        if not self.set_scan_screen(screen_idx):
            screen_idx = 1
            if self.set_scan_screen(screen_idx):
                config.scan_screen = screen_idx

    def run(self):
        logger.debug("Screenshot thread started.")
        while self.shared_state.running:
            try:
                if config.auto_scan_mode and not config.is_enabled:
                    logger.debug(f"paused while auto mode")
                    self._sleep_and_handle_loop_exit(1)
                    continue
                self.shared_state.screenshot_trigger_event.wait()
                self.shared_state.screenshot_trigger_event.clear()
                if not self.shared_state.running: break
                logger.debug("Screenshot: Triggered!")

                # prevent multiple ocr runs during auto_scan_interval_seconds
                seconds_since_last_ocr = time.perf_counter() - self.last_ocr_put_time
                if config.auto_scan_mode and seconds_since_last_ocr < config.auto_scan_interval_seconds:
                    logger.debug(
                        f"...{seconds_since_last_ocr:.2f}s since last ocr, sleeping for another {config.auto_scan_interval_seconds - seconds_since_last_ocr:.2f}s")
                    self._sleep_and_handle_loop_exit(config.auto_scan_interval_seconds - seconds_since_last_ocr)
                    continue

                # prevent ocr runs without mouse movements for auto-on-mouse-move mode
                if config.auto_scan_mode and config.auto_scan_on_mouse_move and self.last_mouse_pos == self.input_loop.get_mouse_pos():
                    continue
                self.last_mouse_pos = self.input_loop.get_mouse_pos()

                logger.debug("screenmanager acquiring lock...")
                with self.shared_state.screen_lock:
                    logger.debug("...successfully acquired lock by screenmanager")
                    start_time = time.perf_counter()
                    screenshot = self.take_screenshot()
                logger.debug("...successfully released lock by screenmanager")
                processing_duration = time.perf_counter() - start_time
                logger.debug(f"Screenshot {screenshot.size} complete in {processing_duration:.2f}s")

                if self.last_screenshot and self.last_screenshot.raw == screenshot.raw:
                    logger.debug(f"Screen content didnt change... skipping ocr")
                    self._sleep_and_handle_loop_exit(0.1)
                    continue

                self.last_screenshot = screenshot
                self.last_mouse_pos = self.input_loop.get_mouse_pos()
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                self.shared_state.ocr_queue.put(img)
                self.last_ocr_put_time = time.perf_counter()
            except:
                logger.exception("An unexpected error occurred in the screenshot loop. Continuing...")
                self._sleep_and_handle_loop_exit(1)
        logger.debug("Screenshot thread stopped.")

    def take_screenshot(self):
        with mss.mss() as sct:
            sct_img = sct.grab(self.monitor)
            return sct_img

    def set_scan_screen(self, screen_index):
        with mss.mss() as sct:
            if 0 <= screen_index < len(sct.monitors):
                logger.info(f"Set scan screen to {screen_index}")
                self.monitor = sct.monitors[screen_index]
                return True

        logger.error(f"Cannot set scan screen: index {screen_index} is out of bounds.")
        return False

    def get_scan_geometry(self):
        if not self.monitor:
            return 0, 0, 0, 0
        return self.monitor["left"], self.monitor["top"], self.monitor["width"], self.monitor["height"]

    def force_screenshot_trigger(self):
        self.last_screenshot = None
        self.last_mouse_pos = None

    def _sleep_and_handle_loop_exit(self, interval):
        if config.auto_scan_mode:
            time.sleep(interval)
            self.shared_state.screenshot_trigger_event.set()
        else:
            self.shared_state.hit_scan_queue.trigger()

    @staticmethod
    def get_screens():
        with mss.mss() as sct:
            return sct.monitors
