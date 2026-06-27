# meikikai/anki/worker.py
import logging
import queue
import threading
from dataclasses import dataclass
from html import escape
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QObject, pyqtSignal

from meikikai.anki.cards import build_vocab_card_payload
from meikikai.anki.connect import (
    AnkiApiError,
    AnkiConnectClient,
    AnkiConnectError,
    AnkiConnectionError,
    AnkiModelSetupError,
    DuplicateNoteError,
    make_note,
    note_exists_for_key,
    setup_meikikai_note_type,
)
from meikikai.config.config import config
from meikikai.tts.shortcuts import (
    ShortcutsTts,
    ShortcutsTtsError,
    cleanup_tts_file,
    convert_caf_to_m4a,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnkiExportRequest:
    lookup_data: object
    screenshot_path: str | None = None


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

    def submit(self, lookup_data, screenshot_path: str | None = None):
        self._queue.put(AnkiExportRequest(lookup_data, screenshot_path))

    def stop(self):
        self._queue.put(None)

    def run(self):
        logger.debug("Anki export worker started.")
        while True:
            request = self._queue.get()
            if request is None:
                break
            try:
                self._export(request)
            except Exception:
                logger.exception("Unexpected Anki export failure.")
                self._notify(
                    "Anki export failed",
                    "Unexpected error while exporting to Anki. Check the MeikiKai log for details.",
                    "critical",
                )
            finally:
                if request.screenshot_path:
                    Path(request.screenshot_path).unlink(missing_ok=True)
        logger.debug("Anki export worker stopped.")

    def _export(self, request: AnkiExportRequest):
        payload = build_vocab_card_payload(request.lookup_data)
        if not payload:
            self._notify("Anki export skipped", "No vocabulary entry is visible to export.", "warning")
            return

        audio_warning = None

        try:
            self._sync_config()
            if not self._setup_complete:
                setup_meikikai_note_type(self._client, self.deck_name, self.model_name)
                self._setup_complete = True
            else:
                self._client.create_deck(self.deck_name)

            if note_exists_for_key(self._client, self.model_name, payload.key):
                raise DuplicateNoteError("MeikiKai duplicate key already exists.")

            if request.screenshot_path:
                self._attach_screenshot(payload.fields, request.screenshot_path)

            if config.anki_attach_tts_audio:
                audio_warning = self._attach_tts_audio(payload)

            note = make_note(self.deck_name, self.model_name, payload.fields)
            self._client.add_note(note)
        except DuplicateNoteError:
            self._notify("Already in Anki", f"{payload.expression} is already in Anki.", "duplicate")
            return
        except AnkiConnectionError:
            self._setup_complete = False
            self._notify(
                "Anki unavailable",
                "Open Anki with AnkiConnect enabled, then press A while the popup is visible.",
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

        if audio_warning:
            self._notify(
                "Added to Anki with audio warning",
                f"{payload.expression} → {self.deck_name}. {audio_warning}",
                "warning",
            )
        else:
            self._notify("Added to Anki", f"{payload.expression} → {self.deck_name}", "success")

    def _attach_screenshot(self, fields: dict[str, str], screenshot_path: str):
        filename = f"meikikai_{uuid4().hex}.png"
        stored_filename = self._client.store_media_file(filename, screenshot_path) or filename
        fields["Screenshot"] = f'<img src="{escape(stored_filename)}">'

    def _attach_tts_audio(self, payload) -> str | None:
        if not config.shortcuts_tts_enabled:
            return "Audio was not attached because Shortcuts TTS is disabled. Enable Speech in Settings."

        return self._attach_tts_audio_field(payload.fields, "WordAudio", payload.word_speech_text)

    def _attach_tts_audio_field(self, fields: dict[str, str], field_name: str, text: str) -> str | None:
        spoken_text = (text or "").strip()
        if not spoken_text:
            return "no text was available."

        caf_path = None
        m4a_path = None
        try:
            caf_path = ShortcutsTts().synthesize_to_caf(spoken_text)
            m4a_path = convert_caf_to_m4a(caf_path)
            filename = f"meikikai_tts_{uuid4().hex}.m4a"
            stored_filename = self._client.store_media_file(filename, str(m4a_path)) or filename
            fields[field_name] = f"[sound:{stored_filename}]"
            return None
        except ShortcutsTtsError as e:
            logger.warning("Could not attach Shortcuts TTS audio to Anki card.", exc_info=True)
            return str(e)
        except AnkiConnectError as e:
            logger.warning("Could not upload Shortcuts TTS audio to Anki.", exc_info=True)
            return f"could not upload generated audio to Anki: {e}"
        finally:
            cleanup_tts_file(caf_path)
            cleanup_tts_file(m4a_path)

    def _sync_config(self):
        if config.anki_connect_url == self.anki_url:
            return

        self.anki_url = config.anki_connect_url
        self._client = AnkiConnectClient(self.anki_url)
        self._setup_complete = False

    def _notify(self, title: str, message: str, level: str):
        self.notifier.message.emit(title, message, level)
