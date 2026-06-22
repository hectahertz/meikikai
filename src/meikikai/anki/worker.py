# meikikai/anki/worker.py
import logging
import queue
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from meikikai.anki.cards import build_vocab_card_payload
from meikikai.anki.connect import (
    AnkiApiError,
    AnkiConnectClient,
    AnkiConnectionError,
    AnkiModelSetupError,
    DuplicateNoteError,
    make_note,
    note_exists_for_key,
    setup_meikikai_note_type,
)
from meikikai.config.config import config

logger = logging.getLogger(__name__)


class AnkiExportNotifier(QObject):
    message = pyqtSignal(str, str, str)


class AnkiExportWorker(threading.Thread):
    def __init__(self, anki_url: str, deck_name: str, model_name: str, notifier: AnkiExportNotifier):
        super().__init__(daemon=True, name="AnkiExportWorker")
        self.anki_url = anki_url
        self.deck_name = deck_name
        self.model_name = model_name
        self.notifier = notifier
        self._queue = queue.Queue()
        self._client = AnkiConnectClient(anki_url)
        self._setup_complete = False

    def submit(self, lookup_data):
        self._queue.put(lookup_data)

    def stop(self):
        self._queue.put(None)

    def run(self):
        logger.debug("Anki export worker started.")
        while True:
            lookup_data = self._queue.get()
            if lookup_data is None:
                break
            try:
                self._export(lookup_data)
            except Exception:
                logger.exception("Unexpected Anki export failure.")
                self._notify(
                    "Anki export failed",
                    "Unexpected error while exporting to Anki. Check the MeikiKai log for details.",
                    "critical",
                )
        logger.debug("Anki export worker stopped.")

    def _export(self, lookup_data):
        payload = build_vocab_card_payload(lookup_data)
        if not payload:
            self._notify("Anki export skipped", "No vocabulary entry is visible to export.", "warning")
            return

        try:
            self._sync_config()
            if not self._setup_complete:
                setup_meikikai_note_type(self._client, self.deck_name, self.model_name)
                self._setup_complete = True

            if note_exists_for_key(self._client, self.model_name, payload.key):
                raise DuplicateNoteError("MeikiKai duplicate key already exists.")

            note = make_note(self.deck_name, self.model_name, payload.fields)
            self._client.add_note(note)
        except DuplicateNoteError:
            self._notify("Already in Anki", f"{payload.expression} is already in Anki.", "duplicate")
            return
        except AnkiConnectionError:
            self._setup_complete = False
            self._notify(
                "Anki unavailable",
                "Open Anki with AnkiConnect enabled, then try Ctrl+Shift+M again.",
                "warning",
            )
            return
        except AnkiModelSetupError as e:
            self._setup_complete = False
            self._notify("Anki setup blocked", str(e), "critical")
            return
        except AnkiApiError as e:
            self._notify("Anki export failed", f"{e.action}: {e.message}", "critical")
            return

        self._notify("Added to Anki", f"{payload.expression} → {self.deck_name}", "success")

    def _sync_config(self):
        if config.anki_connect_url == self.anki_url:
            return

        self.anki_url = config.anki_connect_url
        self._client = AnkiConnectClient(self.anki_url)
        self._setup_complete = False

    def _notify(self, title: str, message: str, level: str):
        self.notifier.message.emit(title, message, level)
