# meikikai/ocr/ocr.py
import logging
import threading
import time
from typing import Optional

from meikikai.ocr.interface import OcrProvider
from meikikai.ocr.providers.chrome_screen_ai import ChromeScreenAiProvider

logger = logging.getLogger(__name__)


class OcrProcessor(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="OcrProcessor")
        self.shared_state = shared_state
        self.ocr_backend: Optional[OcrProvider] = None
        self.last_error: str | None = None
        self._backend_lock = threading.RLock()
        self._load_ocr_backend()

    def run(self):
        logger.debug("OCR thread started.")
        while self.shared_state.running:
            try:
                screenshot = self.shared_state.ocr_queue.get()
                if not self.shared_state.running:
                    break

                logger.debug("OCR: Triggered!")

                with self._backend_lock:
                    ocr_backend = self.ocr_backend

                if not ocr_backend:
                    logger.debug("No OCR backend is available; OCR scan skipped.")
                    self.shared_state.hit_scan_queue.put(None)
                    continue

                start_time = time.perf_counter()
                ocr_result = ocr_backend.scan(screenshot)
                logger.info(
                    f"{ocr_backend.NAME} found {len(ocr_result) if ocr_result else 0} paragraphs in {(time.perf_counter() - start_time):.3f}s.")
                # todo keep last ocr result?

                self.shared_state.hit_scan_queue.put(ocr_result)
            except:
                logger.exception("An unexpected error occurred in the ocr loop. Continuing...")
            finally:
                if self.shared_state.running:
                    self.shared_state.screenshot_trigger_event.set()
        logger.debug("OCR thread stopped.")

    def is_backend_available(self) -> bool:
        with self._backend_lock:
            return self.ocr_backend is not None

    def reload_ocr_backend(self) -> bool:
        return self._load_ocr_backend()

    def unload_ocr_backend(self, reason: str | None = None) -> None:
        with self._backend_lock:
            self.ocr_backend = None
            self.last_error = reason
        self.shared_state.ocr_available_event.clear()
        self.shared_state.hit_scan_queue.put(None)

    def _load_ocr_backend(self) -> bool:
        try:
            ocr_backend = ChromeScreenAiProvider()
        except Exception as e:
            logger.warning(
                "OCR backend '%s' is unavailable: %s.",
                ChromeScreenAiProvider.NAME,
                e,
            )
            with self._backend_lock:
                self.ocr_backend = None
                self.last_error = str(e)
            self.shared_state.ocr_available_event.clear()
            return False

        with self._backend_lock:
            self.ocr_backend = ocr_backend
            self.last_error = None

        self.shared_state.ocr_available_event.set()
        self.shared_state.screenshot_trigger_event.set()
        logger.info(f"Initialized OCR with '{ocr_backend.NAME}' provider.")
        return True
