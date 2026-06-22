# meikikai/anki/connect.py
import logging
from dataclasses import dataclass
from typing import Optional

import requests

from meikikai.anki.cards import (
    BACK_TEMPLATE,
    CARD_CSS,
    FIELD_NAMES,
    FRONT_TEMPLATE,
    TEMPLATE_NAME,
)

logger = logging.getLogger(__name__)

ANKI_CONNECT_VERSION = 6
DEFAULT_TIMEOUT_SECONDS = 2.5


class AnkiConnectError(Exception):
    """Base class for AnkiConnect integration errors."""


class AnkiConnectionError(AnkiConnectError):
    """AnkiConnect could not be reached."""


class AnkiApiError(AnkiConnectError):
    def __init__(self, action: str, message: str):
        super().__init__(message)
        self.action = action
        self.message = message


class AnkiModelSetupError(AnkiConnectError):
    """The MeikiKai note type cannot be safely created or updated."""


class DuplicateNoteError(AnkiConnectError):
    """The card already exists according to MeikiKai's duplicate key."""


@dataclass(frozen=True)
class AnkiNoteSpec:
    deck_name: str
    model_name: str
    fields: dict[str, str]
    tags: list[str]

    def to_anki_connect(self) -> dict:
        return {
            "deckName": self.deck_name,
            "modelName": self.model_name,
            "fields": self.fields,
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "collection",
                "duplicateScopeOptions": {
                    "deckName": self.deck_name,
                    "checkChildren": True,
                    "checkAllModels": False,
                },
            },
            "tags": self.tags,
        }


class AnkiConnectClient:
    def __init__(self, url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def request(self, action: str, params: Optional[dict] = None):
        payload = {
            "action": action,
            "version": ANKI_CONNECT_VERSION,
        }
        if params is not None:
            payload["params"] = params

        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            raise AnkiConnectionError(str(e)) from e

        try:
            data = response.json()
        except ValueError as e:
            raise AnkiConnectionError("AnkiConnect returned a non-JSON response.") from e

        if data.get("error"):
            raise AnkiApiError(action, str(data["error"]))
        return data.get("result")

    def version(self):
        return self.request("version")

    def create_deck(self, deck_name: str):
        return self.request("createDeck", {"deck": deck_name})

    def model_names(self) -> list[str]:
        return list(self.request("modelNames") or [])

    def model_field_names(self, model_name: str) -> list[str]:
        return list(self.request("modelFieldNames", {"modelName": model_name}) or [])

    def model_templates(self, model_name: str) -> dict:
        return dict(self.request("modelTemplates", {"modelName": model_name}) or {})

    def create_model(self, model_name: str):
        return self.request("createModel", {
            "modelName": model_name,
            "inOrderFields": FIELD_NAMES,
            "css": CARD_CSS,
            "isCloze": False,
            "cardTemplates": [{
                "Name": TEMPLATE_NAME,
                "Front": FRONT_TEMPLATE,
                "Back": BACK_TEMPLATE,
            }],
        })

    def update_model_templates(self, model_name: str, template_name: str):
        return self.request("updateModelTemplates", {
            "model": {
                "name": model_name,
                "templates": {
                    template_name: {
                        "Front": FRONT_TEMPLATE,
                        "Back": BACK_TEMPLATE,
                    }
                },
            }
        })

    def update_model_styling(self, model_name: str):
        return self.request("updateModelStyling", {
            "model": {
                "name": model_name,
                "css": CARD_CSS,
            }
        })

    def model_template_add(self, model_name: str):
        return self.request("modelTemplateAdd", {
            "modelName": model_name,
            "template": {
                "Name": TEMPLATE_NAME,
                "Front": FRONT_TEMPLATE,
                "Back": BACK_TEMPLATE,
            },
        })

    def model_template_remove(self, model_name: str, template_name: str):
        return self.request("modelTemplateRemove", {
            "modelName": model_name,
            "templateName": template_name,
        })

    def model_field_add(self, model_name: str, field_name: str, index: int):
        return self.request("modelFieldAdd", {
            "modelName": model_name,
            "fieldName": field_name,
            "index": index,
        })

    def model_field_reposition(self, model_name: str, field_name: str, index: int):
        return self.request("modelFieldReposition", {
            "modelName": model_name,
            "fieldName": field_name,
            "index": index,
        })

    def find_notes(self, query: str) -> list[int]:
        return list(self.request("findNotes", {"query": query}) or [])

    def add_note(self, note: AnkiNoteSpec):
        try:
            return self.request("addNote", {"note": note.to_anki_connect()})
        except AnkiApiError as e:
            if "duplicate" in e.message.lower():
                raise DuplicateNoteError(e.message) from e
            raise


def setup_meikikai_note_type(client: AnkiConnectClient, deck_name: str, model_name: str):
    client.version()
    client.create_deck(deck_name)

    if model_name not in client.model_names():
        logger.info("Creating Anki note type '%s'.", model_name)
        client.create_model(model_name)
        return

    fields = client.model_field_names(model_name)
    has_notes = bool(client.find_notes(_model_query(model_name)))
    if not _fields_compatible(fields):
        if has_notes:
            raise AnkiModelSetupError(
                f"Anki note type '{model_name}' exists but is not compatible with MeikiKai "
                "and already contains notes. Please rename it, remove those notes, or create a backup "
                "before replacing it. Required: field 'Key' first, then MeikiKai vocab fields."
            )

        logger.info("Repairing empty incompatible Anki note type '%s'.", model_name)
        _repair_empty_model_fields(client, model_name, fields)
        fields = client.model_field_names(model_name)
        if not _fields_compatible(fields):
            raise AnkiModelSetupError(
                f"Could not safely repair empty Anki note type '{model_name}'."
            )

    template_name = _template_name_to_update(client, model_name, has_notes)
    client.update_model_templates(model_name, template_name)
    client.update_model_styling(model_name)


def note_exists_for_key(client: AnkiConnectClient, model_name: str, key: str) -> bool:
    return bool(client.find_notes(f'{_model_query(model_name)} Key:{_quote_query_value(key)}'))


def make_note(deck_name: str, model_name: str, fields: dict[str, str]) -> AnkiNoteSpec:
    return AnkiNoteSpec(
        deck_name=deck_name,
        model_name=model_name,
        fields=fields,
        tags=["meikikai", "meikikai-vocab"],
    )


def _fields_compatible(fields: list[str]) -> bool:
    return bool(fields) and fields[0] == "Key" and all(field in fields for field in FIELD_NAMES)


def _repair_empty_model_fields(client: AnkiConnectClient, model_name: str, fields: list[str]):
    current = list(fields)
    for index, field_name in enumerate(FIELD_NAMES):
        if field_name not in current:
            client.model_field_add(model_name, field_name, index)
            current.insert(index, field_name)
        else:
            client.model_field_reposition(model_name, field_name, index)
            current.remove(field_name)
            current.insert(index, field_name)


def _template_name_to_update(client: AnkiConnectClient, model_name: str, has_notes: bool) -> str:
    templates = client.model_templates(model_name)
    if not templates:
        if has_notes:
            raise AnkiModelSetupError(
                f"Anki note type '{model_name}' has notes but no card templates. "
                "MeikiKai cannot safely repair it."
            )
        client.model_template_add(model_name)
        return TEMPLATE_NAME

    if len(templates) > 1 and has_notes:
        raise AnkiModelSetupError(
            f"Anki note type '{model_name}' has multiple card templates and contains notes. "
            "MeikiKai expects one vocabulary card template and will not modify existing cards silently."
        )

    if has_notes:
        return TEMPLATE_NAME if TEMPLATE_NAME in templates else next(iter(templates))

    client.model_template_add(model_name)
    for template_name in list(templates):
        if template_name != TEMPLATE_NAME:
            client.model_template_remove(model_name, template_name)
    return TEMPLATE_NAME


def _model_query(model_name: str) -> str:
    return f"note:{_quote_query_value(model_name)}"


def _quote_query_value(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
