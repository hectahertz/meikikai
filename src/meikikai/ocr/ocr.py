# meikikai/ocr/ocr.py
import logging
import sys
import threading
import time
from typing import Optional

from meikikai.config.config import config
from meikikai.ocr.interface import OcrProvider
from meikikai.ocr.providers.meikiocr import MeikiOcrProvider

logger = logging.getLogger(__name__)


class OcrProcessor(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="OcrProcessor")
        self.shared_state = shared_state
        self.ocr_backend: Optional[OcrProvider] = None
        self._load_ocr_backend()

    def run(self):
        logger.debug("OCR thread started.")
        while self.shared_state.running:
            try:
                screenshot = self.shared_state.ocr_queue.get()
                if not self.shared_state.running:
                    break

                logger.debug("OCR: Triggered!")

                start_time = time.perf_counter()
                ocr_result = self.ocr_backend.scan(screenshot)
                logger.info(
                    f"{self.ocr_backend.NAME} found {len(ocr_result) if ocr_result else 0} paragraphs in {(time.perf_counter() - start_time):.3f}s.")
                # todo keep last ocr result?

                self.shared_state.hit_scan_queue.put(ocr_result)
            except:
                logger.exception("An unexpected error occurred in the ocr loop. Continuing...")
            finally:
                if config.auto_scan_mode:
                    self.shared_state.screenshot_trigger_event.set()
        logger.debug("OCR thread stopped.")

    def _load_ocr_backend(self):
        try:
            self.ocr_backend = MeikiOcrProvider()
            logger.info(f"Initialized OCR with '{self.ocr_backend.NAME}' provider.")
        except Exception as e:
            logger.critical(f"Failed to instantiate '{MeikiOcrProvider.NAME}' on startup: {e}", exc_info=True)
            self.ocr_backend = None
            sys.exit(1)
