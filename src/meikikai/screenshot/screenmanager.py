# meikikai/screenshot/screenmanager.py
import logging
import threading
import time

import mss
from PIL import Image

from meikikai.config.config import config

logger = logging.getLogger(__name__)

MOUSE_POLL_INTERVAL_SECONDS = 0.1
CURSOR_REGION_FRACTION = 0.1


# todo doesnt work when monitors change
class ScreenManager(threading.Thread):
    def __init__(self, shared_state, input_loop):
        super().__init__(daemon=True, name="ScreenManager")
        self.shared_state = shared_state
        self.input_loop = input_loop
        self.monitor = None
        self.last_ocr_put_time = 0.0
        self.last_screenshot = None
        self.last_scan_mouse_pos = None
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
                if config.is_paused:
                    logger.debug("paused")
                    self._sleep_and_retrigger(1)
                    continue
                if not self.shared_state.ocr_available_event.is_set():
                    self.shared_state.screenshot_trigger_event.clear()
                    time.sleep(0.25)
                    continue
                self.shared_state.screenshot_trigger_event.wait()
                self.shared_state.screenshot_trigger_event.clear()
                if not self.shared_state.running: break
                logger.debug("Screenshot: Triggered!")

                mouse_pos = self.input_loop.mouse_pos
                if mouse_pos == self.last_scan_mouse_pos:
                    self._sleep_and_retrigger(MOUSE_POLL_INTERVAL_SECONDS)
                    continue

                # prevent multiple ocr runs during auto_scan_interval_seconds
                seconds_since_last_ocr = time.perf_counter() - self.last_ocr_put_time
                if seconds_since_last_ocr < config.auto_scan_interval_seconds:
                    logger.debug(
                        f"...{seconds_since_last_ocr:.2f}s since last ocr, sleeping for another {config.auto_scan_interval_seconds - seconds_since_last_ocr:.2f}s")
                    self._sleep_and_retrigger(config.auto_scan_interval_seconds - seconds_since_last_ocr)
                    continue

                logger.debug("screenmanager acquiring lock...")
                with self.shared_state.screen_lock:
                    logger.debug("...successfully acquired lock by screenmanager")
                    start_time = time.perf_counter()
                    mouse_pos = self.input_loop.mouse_pos
                    screenshot = self.take_screenshot()
                self.last_scan_mouse_pos = mouse_pos
                logger.debug("...successfully released lock by screenmanager")
                processing_duration = time.perf_counter() - start_time
                logger.debug(f"Screenshot {screenshot.size} complete in {processing_duration:.2f}s")

                if self.last_screenshot and not self._has_change_near_cursor(self.last_screenshot, screenshot, mouse_pos):
                    logger.debug(f"Screen content near the cursor didnt change... skipping ocr")
                    self._sleep_and_retrigger(MOUSE_POLL_INTERVAL_SECONDS)
                    continue

                self.last_screenshot = screenshot
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                self.shared_state.ocr_queue.put(img)
                self.last_ocr_put_time = time.perf_counter()
            except:
                logger.exception("An unexpected error occurred in the screenshot loop. Continuing...")
                self._sleep_and_retrigger(1)
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
                self.last_screenshot = None
                self.last_scan_mouse_pos = None
                return True

        logger.error(f"Cannot set scan screen: index {screen_index} is out of bounds.")
        return False

    def get_scan_geometry(self):
        if not self.monitor:
            return 0, 0, 0, 0
        return self.monitor["left"], self.monitor["top"], self.monitor["width"], self.monitor["height"]

    def _has_change_near_cursor(self, previous, current, mouse_pos):
        if previous.size != current.size:
            return True
        if previous.raw == current.raw:
            return False

        width, height = current.size
        left, top, scan_width, scan_height = self.get_scan_geometry()
        if not scan_width or not scan_height:
            return True
        mouse_x, mouse_y = mouse_pos
        cursor_x = int((mouse_x - left) / scan_width * width)
        cursor_y = int((mouse_y - top) / scan_height * height)
        if not (0 <= cursor_x < width and 0 <= cursor_y < height):
            return False

        band_width = max(1, int(width * CURSOR_REGION_FRACTION))
        band_height = max(1, int(height * CURSOR_REGION_FRACTION))
        regions = (
            (0, max(0, cursor_y - band_height), width, min(height, cursor_y + band_height + 1)),
            (max(0, cursor_x - band_width), 0, min(width, cursor_x + band_width + 1), height),
        )
        previous_image = Image.frombuffer("RGBA", previous.size, previous.raw, "raw", "RGBA", 0, 1)
        current_image = Image.frombuffer("RGBA", current.size, current.raw, "raw", "RGBA", 0, 1)
        return any(previous_image.crop(region).tobytes() != current_image.crop(region).tobytes() for region in regions)

    def _sleep_and_retrigger(self, interval):
        time.sleep(interval)
        if self.shared_state.running:
            self.shared_state.screenshot_trigger_event.set()

    @staticmethod
    def get_screens():
        with mss.mss() as sct:
            return sct.monitors
