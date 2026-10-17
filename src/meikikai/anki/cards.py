# meikikai/anki/cards.py
from dataclasses import dataclass
from html import escape
from typing import Iterable, Optional

from meikikai.dictionary.customdict import DEFAULT_FREQ
from meikikai.dictionary.lookup import DictionaryEntry, KanjiEntry, LookupResult
from meikikai.gui.popup_design.tokens import PAPER_THEME_VARIANTS, POPUP

MAX_GLOSSES_PER_SENSE = POPUP.max_glosses_per_sense
MAX_SENSES_PER_ENTRY = POPUP.max_senses_per_entry
PAPER_LIGHT = PAPER_THEME_VARIANTS["light"]
PAPER_DARK = PAPER_THEME_VARIANTS["dark"]

DECK_NAME = "MeikiKai Mining"
MODEL_NAME = "MeikiKai Vocab"
TEMPLATE_NAME = "Recognition"

FIELD_NAMES = [
    "Key",
    "Expression",
    "Reading",
    "WordAudio",
    "LookupText",
    "Sentence",
    "SentenceHighlighted",
    "Screenshot",
    "PrimaryDefinition",
    "Definitions",
    "PartOfSpeech",
    "Tags",
    "FrequencyRank",
    "Deconjugation",
    "KanjiInfo",
    "EntryID",
]

SENTENCE_BREAKS = set("。！？!?\n")
CLOSING_QUOTES = set("」』）】〉》\"'")


@dataclass(frozen=True)
class VocabCardPayload:
    key: str
    expression: str
    word_speech_text: str
    fields: dict[str, str]


def top_dictionary_entry(data) -> Optional[DictionaryEntry]:
    entries = entries_from_data(data)
    for entry in entries:
        if isinstance(entry, DictionaryEntry):
            return entry
    return None


def entries_from_data(data) -> list[DictionaryEntry | KanjiEntry]:
    if isinstance(data, LookupResult):
        return list(data.entries)
    if data:
        return list(data)
    return []


def duplicate_key(entry: DictionaryEntry) -> str:
    return f"v:{entry.id}:{entry.written_form}:{entry.reading}"


def build_vocab_card_payload(data) -> Optional[VocabCardPayload]:
    entry = top_dictionary_entry(data)
    if not entry:
        return None

    entries = entries_from_data(data)
    sentence, sentence_highlighted = _sentence_fields(entry, data)
    definitions_html = _definitions_html(entry)
    primary_definition = _primary_definition_html(entry)
    shown_senses = _shown_definition_senses(entry.senses)
    pos_values = _unique_sense_values(shown_senses, "pos")
    tag_values = _unique_sense_values(shown_senses, "tags")
    deconj = _deconjugation_text(entry)
    key = duplicate_key(entry)

    fields = {name: "" for name in FIELD_NAMES}
    fields.update({
        "Key": key,
        "Expression": _escape(entry.written_form),
        "Reading": _escape(entry.reading),
        "LookupText": _escape(_lookup_text(data, entry)),
        "Sentence": sentence,
        "SentenceHighlighted": sentence_highlighted,
        "PrimaryDefinition": primary_definition,
        "Definitions": definitions_html,
        "PartOfSpeech": _join_escaped(pos_values, " · "),
        "Tags": _join_escaped(tag_values, " · "),
        "FrequencyRank": f"#{entry.freq}" if entry.freq < DEFAULT_FREQ else "",
        "Deconjugation": _escape(deconj),
        "KanjiInfo": _kanji_info_html(entries),
        "EntryID": str(entry.id),
    })
    word_speech_text = (entry.reading or entry.written_form or "").strip()
    return VocabCardPayload(
        key=key,
        expression=entry.written_form,
        word_speech_text=word_speech_text,
        fields=fields,
    )


def _lookup_text(data, entry: DictionaryEntry) -> str:
    if isinstance(data, LookupResult):
        return data.lookup_text or (data.context.lookup_text if data.context else "") or entry.matched_text or entry.written_form
    return entry.matched_text or entry.written_form


def _sentence_fields(entry: DictionaryEntry, data) -> tuple[str, str]:
    fallback = entry.matched_text or entry.written_form
    if not isinstance(data, LookupResult) or not data.context:
        word = _escape(fallback)
        return word, f'<span class="mk-highlight">{word}</span>'

    full_text = data.context.full_text or ""
    hit_index = data.context.hit_index
    target_len = entry.match_len or len(entry.matched_text) or len(entry.written_form)
    if not full_text or hit_index < 0 or hit_index >= len(full_text) or target_len <= 0:
        word = _escape(fallback)
        return word, f'<span class="mk-highlight">{word}</span>'

    start, end = _sentence_bounds(full_text, hit_index, target_len)
    while start < end and full_text[start].isspace():
        start += 1
    while end > start and full_text[end - 1].isspace():
        end -= 1

    if start >= end:
        word = _escape(fallback)
        return word, f'<span class="mk-highlight">{word}</span>'

    sentence = full_text[start:end]
    highlight_start = max(0, min(hit_index - start, len(sentence)))
    highlight_end = max(highlight_start, min(hit_index + target_len - start, len(sentence)))
    if highlight_start == highlight_end:
        word = _escape(fallback)
        return word, f'<span class="mk-highlight">{word}</span>'

    plain = _escape(sentence)
    highlighted = (
        _escape(sentence[:highlight_start])
        + f'<span class="mk-highlight">{_escape(sentence[highlight_start:highlight_end])}</span>'
        + _escape(sentence[highlight_end:])
    )
    return plain, highlighted


def _sentence_bounds(full_text: str, hit_index: int, target_len: int) -> tuple[int, int]:
    start = 0
    for i in range(min(hit_index, len(full_text) - 1), -1, -1):
        if full_text[i] in SENTENCE_BREAKS:
            start = i + 1
            break

    end = len(full_text)
    scan_from = min(len(full_text), hit_index + max(1, target_len))
    for i in range(scan_from, len(full_text)):
        if full_text[i] in SENTENCE_BREAKS:
            end = i + 1
            while end < len(full_text) and full_text[end] in CLOSING_QUOTES:
                end += 1
            break
    return start, end


def _definitions_html(entry: DictionaryEntry) -> str:
    sense_parts = []
    for sense in _shown_definition_senses(entry.senses):
        glosses = [_gloss_to_html(gloss) for gloss in sense.get("glosses", []) if gloss]
        sense_parts.append(", ".join(glosses[:MAX_GLOSSES_PER_SENSE]))

    if len(sense_parts) <= 1:
        return sense_parts[0] if sense_parts else ""

    rows = []
    for index, sense_text in enumerate(sense_parts, 1):
        rows.append(
            f'<div class="mk-sense"><span class="mk-sense-number">{index}</span>'
            f'{sense_text}</div>'
        )
    return "".join(rows)


def _shown_definition_senses(senses: list) -> list:
    shown_senses = []
    for sense in senses:
        if not sense.get("glosses"):
            continue
        shown_senses.append(sense)
        if len(shown_senses) >= MAX_SENSES_PER_ENTRY:
            break
    return shown_senses


def _primary_definition_html(entry: DictionaryEntry) -> str:
    for sense in entry.senses:
        for gloss in sense.get("glosses", []):
            if gloss:
                return _gloss_to_html(gloss)
    return ""


def _unique_sense_values(senses: list, key: str) -> list[str]:
    values = []
    seen = set()
    for sense in senses:
        for value in sense.get(key, []):
            if value and value not in seen:
                seen.add(value)
                values.append(value)
    return values


def _deconjugation_text(entry: DictionaryEntry) -> str:
    if not entry.deconjugation_process:
        return ""
    steps = [p for p in entry.deconjugation_process if p]
    if steps and steps[0] == entry.written_form:
        steps = steps[1:]
    return " · ".join(steps)


def _kanji_info_html(entries: Iterable[DictionaryEntry | KanjiEntry]) -> str:
    cards = [_kanji_card_html(entry) for entry in entries if isinstance(entry, KanjiEntry)]
    return "".join(cards)


def _kanji_card_html(entry: KanjiEntry) -> str:
    readings = _join_escaped(entry.readings)
    meanings = _join_escaped(entry.meanings)
    examples = _kanji_examples_html(entry)
    components = _kanji_components_html(entry)

    details = []
    if readings:
        details.append(f'<div class="mk-kanji-reading">{readings}</div>')
    if meanings:
        details.append(f'<div class="mk-kanji-meanings">{meanings}</div>')

    detail_rows = []
    if examples:
        detail_rows.append(_kanji_detail_row_html("ex", examples))
    if components:
        detail_rows.append(_kanji_detail_row_html("parts", components))
    if detail_rows:
        details.append(f'<div class="mk-kanji-detail-group">{"".join(detail_rows)}</div>')

    return (
        '<div class="mk-kanji-card">'
        f'<div class="mk-kanji-glyph">{_escape(entry.character)}</div>'
        f'<div class="mk-kanji-body">{"".join(details)}</div>'
        '</div>'
    )


def _kanji_detail_row_html(label: str, body: str) -> str:
    return (
        '<div class="mk-kanji-detail">'
        f'<span class="mk-kanji-detail-label">{label}</span>'
        f'<span class="mk-kanji-detail-body">{body}</span>'
        '</div>'
    )


def _kanji_examples_html(entry: KanjiEntry) -> str:
    parts = []
    for ex in entry.examples:
        word = _escape(ex.get("w", ""))
        reading = _escape(ex.get("r", ""))
        meaning = _escape(ex.get("m", ""))
        if word or reading or meaning:
            parts.append(
                f'<span class="mk-kanji-example-word">{word}</span> '
                f'<span class="mk-kanji-example-reading">{reading}</span> {meaning}'
            )
    if not parts:
        return ""
    return "; ".join(parts)


def _kanji_components_html(entry: KanjiEntry) -> str:
    parts = []
    for component in entry.components:
        char = _escape(component.get("c", ""))
        meaning = _escape(component.get("m", ""))
        if meaning:
            parts.append(f'<span class="mk-component-char">{char}</span> {meaning}')
        elif char:
            parts.append(f'<span class="mk-component-char">{char}</span>')
    if not parts:
        return ""
    return " · ".join(parts)


def _escape(value) -> str:
    return escape(str(value), quote=False)


def _contains_html(value: str) -> bool:
    return "<" in value and ">" in value


def _gloss_to_html(gloss) -> str:
    text = str(gloss).strip()
    if _contains_html(text):
        return text
    return _escape(text)


def _join_escaped(values, separator=", ") -> str:
    return separator.join(_escape(value) for value in values if value)


META_TEMPLATE = """
  <div class="mk-meta">
    <span><span class="mk-meta-label">MeikiKai</span>{{#FrequencyRank}} · {{FrequencyRank}}{{/FrequencyRank}}</span>
    <a class="mk-link" href="https://jisho.org/search/{{text:Expression}}">jisho ↗</a>
  </div>
  <div class="mk-prompt"><div class="mk-sentence">{{SentenceHighlighted}}</div></div>
""".strip("\n")

FRONT_TEMPLATE = (
    '<div class="mk mk-front">\n'
    + META_TEMPLATE
    + '\n  <div class="mk-rule-row"></div>\n</div>'
)

BACK_TEMPLATE = (
    '<div class="mk mk-back">\n'
    + META_TEMPLATE
    + """
  {{#WordAudio}}<div class="mk-rule-row mk-audio">{{WordAudio}}</div>{{/WordAudio}}
  {{^WordAudio}}<div class="mk-rule-row"></div>{{/WordAudio}}

  <div class="mk-answer">
    {{#Screenshot}}<div class="mk-screenshot">{{Screenshot}}</div>{{/Screenshot}}
    {{#PrimaryDefinition}}<div class="mk-meaning">{{PrimaryDefinition}}</div>{{/PrimaryDefinition}}
    <div class="mk-term">
      <span class="mk-word">{{Expression}}</span>
      {{#Reading}}<span class="mk-reading">{{Reading}}</span>{{/Reading}}
    </div>
    <div class="mk-pos"><span>{{PartOfSpeech}}</span><span>{{Tags}}</span></div>

    <div class="mk-notes">
      {{#Definitions}}
      <div class="mk-note">
        <div class="mk-note-label">Definitions</div>
        <div class="mk-note-body mk-definitions">{{Definitions}}</div>
      </div>
      {{/Definitions}}
      {{#Deconjugation}}
      <div class="mk-note">
        <div class="mk-note-label">Inflected</div>
        <div class="mk-note-body mk-deconj">{{Deconjugation}}</div>
      </div>
      {{/Deconjugation}}
      {{KanjiInfo}}
    </div>
  </div>
</div>"""
)


def _paper_variables(tokens) -> str:
    return (
        f"  --page: {tokens.surface_bg};\n"
        f"  --ink: {tokens.text};\n"
        f"  --muted: {tokens.muted_text};\n"
        f"  --rule: {tokens.separator};\n"
        f"  --accent: {tokens.deconjugation_text};\n"
    )


CARD_CSS = (
    ".card {\n"
    + _paper_variables(PAPER_LIGHT)
    + """  --ui: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "Hiragino Sans", sans-serif;
  --serif: "Iowan Old Style", "Palatino", Georgia, "Hiragino Mincho ProN", serif;
  --jp: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  margin: 0;
  padding: 0;
  background: var(--page);
  color: var(--ink);
  font-family: var(--ui);
  font-size: 16px;
  line-height: 1.5;
  text-align: left;
  -webkit-text-size-adjust: 100%;
}
.card.nightMode, .card.night_mode {
"""
    + _paper_variables(PAPER_DARK)
    + """  background: var(--page);
}
.card * { box-sizing: border-box; }

.mk {
  display: flex;
  flex-direction: column;
  max-width: 720px;
  margin: 0 auto;
  padding: 14px 20px 36px;
}
@media (min-width: 600px) {
  .mk { margin: 24px auto; padding: 18px 36px 40px; }
}

.mk-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: .03em;
}
.mk-meta-label { font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.mk-link { color: var(--muted) !important; text-decoration: none; }

.mk-prompt { display: flex; justify-content: center; padding: 28px 0 14px; }
.mk-sentence {
  max-width: 100%;
  font-family: var(--jp);
  font-size: 36px;
  font-weight: 500;
  line-height: 1.95;
  text-align: start;
  overflow-wrap: anywhere;
}
.mk-highlight { color: var(--accent); background: none; font-weight: inherit; text-decoration: none; }

.mk-rule-row {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
}
.mk-rule-row:not(.mk-audio)::before { content: ""; width: 40px; height: 1px; background: var(--rule); }
.mk-audio::before, .mk-audio::after {
  content: "";
  position: absolute;
  top: 50%;
  width: 56px;
  height: 1px;
  background: var(--rule);
}
.mk-audio::before { right: calc(50% + 32px); }
.mk-audio::after { left: calc(50% + 32px); }
.mk-audio .replay-button, .mk-audio .replaybutton { display: inline-flex; width: 40px; height: 40px; margin: 0; }
.mk-audio .replay-button svg, .mk-audio .replaybutton svg { width: 40px; height: 40px; }
.mk-audio .replay-button svg circle, .mk-audio .replaybutton svg circle { fill: none; stroke: var(--rule); stroke-width: 2; }
.mk-audio .replay-button svg path, .mk-audio .replaybutton svg path {
  fill: var(--muted);
  transform: scale(.62);
  transform-origin: 32px 32px;
}

.mk-answer {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 22px;
  text-align: center;
  overflow-wrap: anywhere;
}
.mk-screenshot { margin-bottom: 22px; }
.mk-screenshot img { display: block; max-width: 100%; max-height: 300px; height: auto; margin: 0 auto; }
.mk-meaning { font-family: var(--serif); font-size: 26px; line-height: 1.3; }
.mk-term { margin-top: 8px; color: var(--muted); font-size: 15px; }
.mk-word { margin-right: 8px; color: var(--ink); font-family: var(--jp); font-weight: 500; }
.mk-reading { font-family: var(--jp); }
.mk-pos { margin-top: 2px; color: var(--muted); font-size: 12px; letter-spacing: .03em; }
.mk-pos span:empty { display: none; }
.mk-pos span:not(:empty) + span:not(:empty)::before { content: " · "; }

.mk-notes {
  display: grid;
  gap: 16px;
  width: 100%;
  max-width: 34em;
  margin: 22px auto 0;
  color: var(--ink);
  font-size: 15px;
  text-align: left;
}
.mk-notes:empty { display: none; }
.mk-note, .mk-kanji-card { border-left: 2px solid var(--accent); padding: 2px 0 2px 14px; }
.mk-note-label, .mk-kanji-detail-label {
  color: var(--accent);
  font-size: 11px;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.mk-note-label { margin-bottom: 4px; }
.mk-note-body { line-height: 1.6; }
.mk-definitions { font-family: var(--serif); font-size: 17px; }
.mk-sense { padding-left: 22px; text-indent: -22px; }
.mk-sense-number {
  display: inline-block;
  width: 22px;
  color: var(--accent);
  text-indent: 0;
  font-family: var(--ui);
  font-size: 13px;
}
.mk-deconj { color: var(--muted); }

.mk-kanji-card { display: flex; align-items: flex-start; gap: 14px; }
.mk-kanji-glyph { flex: none; font-family: var(--jp); font-size: 40px; font-weight: 500; line-height: 1.1; }
.mk-kanji-body { flex: 1; min-width: 0; line-height: 1.5; }
.mk-kanji-reading { color: var(--muted); font-family: var(--jp); font-size: 14px; }
.mk-kanji-meanings { font-family: var(--serif); font-size: 16px; }
.mk-kanji-detail-group { display: grid; gap: 4px; margin-top: 6px; }
.mk-kanji-detail { display: flex; gap: 10px; color: var(--muted); font-size: 13px; line-height: 1.5; }
.mk-kanji-detail-label { flex: 0 0 4.4em; padding-top: 1px; white-space: nowrap; }
.mk-kanji-detail-body { flex: 1; min-width: 0; }
.mk-kanji-example-word, .mk-component-char { color: var(--ink); font-family: var(--jp); font-weight: 500; }
.mk-kanji-example-reading { font-family: var(--jp); }

@media (max-width: 480px) {
  .mk { padding-left: 12px; padding-right: 12px; }
  .mk-prompt { padding-top: 20px; }
  .mk-sentence { font-size: 30px; }
  .mk-meaning { font-size: 23px; }
}
""".strip()
)
