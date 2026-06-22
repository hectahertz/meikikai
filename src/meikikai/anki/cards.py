# meikikai/anki/cards.py
from dataclasses import dataclass
from html import escape
from typing import Iterable, Optional

from meikikai.dictionary.customdict import DEFAULT_FREQ
from meikikai.dictionary.lookup import DictionaryEntry, KanjiEntry, LookupResult
from meikikai.gui.popup import (
    DECONJ_COLOR,
    DEFINITION_COLOR,
    DEFINITION_FONT_SIZE,
    DETAIL_FONT_SIZE,
    FONT_STACK_QSS,
    KANJI_GLYPH_FONT_SIZE,
    MAX_GLOSSES_PER_SENSE,
    MAX_SENSES_PER_ENTRY,
    META_FONT_SIZE,
    META_LABEL_COLOR,
    MUTED_COLOR,
    POPUP_WIDTH,
    READING_COLOR,
    READING_FONT_SIZE,
    SENSE_NUMBER_COLOR,
    TEXT_COLOR,
    WORD_COLOR,
    WORD_FONT_SIZE,
)

DECK_NAME = "MeikiKai Mining"
MODEL_NAME = "MeikiKai Vocab"
TEMPLATE_NAME = "Recognition"

FIELD_NAMES = [
    "Key",
    "Expression",
    "Reading",
    "LookupText",
    "Sentence",
    "SentenceHighlighted",
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
    return VocabCardPayload(key=key, expression=entry.written_form, fields=fields)


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
            f'<span class="mk-sense-number">{index}</span>'
            f'&nbsp;{sense_text}'
        )
    return "<br>".join(rows)


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
        details.append(f'<div class="mk-kanji-reading">[{readings}]</div>')
    if meanings:
        details.append(f'<div class="mk-kanji-meanings">{meanings}</div>')
    if examples:
        details.append(f'<div class="mk-kanji-detail">{examples}</div>')
    if components:
        details.append(f'<div class="mk-kanji-detail">{components}</div>')

    return (
        '<div class="mk-kanji-card">'
        f'<div class="mk-kanji-glyph">{_escape(entry.character)}</div>'
        f'<div class="mk-kanji-body">{"".join(details)}</div>'
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
                f'<span class="mk-kanji-example-reading">[{reading}]</span> {meaning}'
            )
    if not parts:
        return ""
    return f'<span class="mk-label">ex</span> {"; ".join(parts)}'


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
    return f'<span class="mk-label">parts</span> {" · ".join(parts)}'


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


FRONT_TEMPLATE = """
<div class="mk-card mk-front-card mk-card-root">
  <div class="mk-front-sentence">{{SentenceHighlighted}}</div>
</div>
""".strip()

BACK_TEMPLATE = """
<div class="mk-back-layout mk-card-root">
  <div class="mk-card mk-front-card mk-back-sentence-card">
    <div class="mk-front-sentence">{{SentenceHighlighted}}</div>
  </div>

  <div class="mk-card mk-popup-card">
    <div class="mk-entry">
      <div class="mk-word-row">
        <span class="mk-word">{{Expression}}</span>
        {{#Reading}}<span class="mk-reading">[{{Reading}}]</span>{{/Reading}}
      </div>

      <div class="mk-meta-row">
        {{#PartOfSpeech}}<span>{{PartOfSpeech}}</span>{{/PartOfSpeech}}
        {{#Tags}}{{#PartOfSpeech}}<span class="mk-dot">·</span>{{/PartOfSpeech}}<span>{{Tags}}</span>{{/Tags}}
        {{#FrequencyRank}}{{#PartOfSpeech}}<span class="mk-dot">·</span>{{/PartOfSpeech}}{{^PartOfSpeech}}{{#Tags}}<span class="mk-dot">·</span>{{/Tags}}{{/PartOfSpeech}}<span>{{FrequencyRank}}</span>{{/FrequencyRank}}
      </div>

      {{#Deconjugation}}
      <div class="mk-deconj"><span class="mk-label">inflected</span> <span class="mk-dot">·</span> {{Deconjugation}}</div>
      {{/Deconjugation}}

      {{#Definitions}}<div class="mk-definitions">{{Definitions}}</div>{{/Definitions}}
    </div>

    {{#KanjiInfo}}<div class="mk-kanji-section">{{KanjiInfo}}</div>{{/KanjiInfo}}
  </div>
</div>
""".strip()

CARD_CSS = f"""
.card {{
  margin: 0;
  background: #11131a;
  color: {TEXT_COLOR};
  font-family: {FONT_STACK_QSS};
  font-size: {DEFINITION_FONT_SIZE}px;
  line-height: 1.42;
  text-align: left;
}}

.mk-card,
.mk-back-layout {{
  width: {POPUP_WIDTH}px;
  max-width: calc(100vw - 24px);
  margin: 0 auto;
  box-sizing: border-box;
}}

.mk-card-root {{
  margin-top: 28px;
}}

.mk-front-card,
.mk-popup-card {{
  background: #181b24;
  color: {TEXT_COLOR};
  border: 1px solid rgba(237, 241, 247, 0.13);
  border-radius: 16px;
  padding: 10px 12px 14px;
}}

.mk-front-card {{
  padding: 17px 18px 18px;
}}

.mk-back-sentence-card {{
  margin-bottom: 14px;
}}

.mk-front-sentence {{
  color: {TEXT_COLOR};
  font-size: 22px;
  line-height: 1.5;
  letter-spacing: 0.01em;
  font-weight: 400;
}}

.mk-context-strip {{
  box-sizing: border-box;
  width: {POPUP_WIDTH}px;
  max-width: calc(100vw - 24px);
  margin: 0 auto 8px;
  padding: 0 2px;
  color: {MUTED_COLOR};
  font-size: 14px;
  line-height: 1.5;
}}

.mk-highlight {{
  color: inherit;
  background: transparent;
  padding: 0;
  font-weight: 500;
  text-decoration: underline;
  text-decoration-color: {WORD_COLOR};
  text-decoration-thickness: 0.12em;
  text-underline-offset: 0.16em;
}}

.mk-word-row {{
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px 8px;
}}

.mk-word {{
  color: {WORD_COLOR};
  font-size: {WORD_FONT_SIZE}px;
  line-height: 1.16;
  font-weight: 500;
}}

.mk-reading {{
  color: {READING_COLOR};
  font-size: {READING_FONT_SIZE}px;
  font-weight: 700;
}}

.mk-meta-row {{
  margin-top: 1px;
  color: #929cae;
  font-size: {META_FONT_SIZE}px;
  line-height: 1.25;
}}

.mk-meta-row:empty {{
  display: none;
}}

.mk-dot {{
  color: {META_LABEL_COLOR};
  margin: 0 5px;
}}

.mk-label {{
  color: {META_LABEL_COLOR};
  font-weight: 800;
}}

.mk-deconj {{
  margin-top: 2px;
  color: {DECONJ_COLOR};
  font-size: {META_FONT_SIZE}px;
  line-height: 1.25;
}}

.mk-definitions {{
  margin-top: 5px;
  color: {DEFINITION_COLOR};
  font-size: {DEFINITION_FONT_SIZE}px;
  line-height: 1.45;
  font-weight: 400;
}}

.mk-sense-number {{
  color: {SENSE_NUMBER_COLOR};
  font-weight: 800;
}}

.mk-kanji-section {{
  margin-top: 8px;
}}

.mk-kanji-card {{
  display: flex;
  gap: 9px;
  box-sizing: border-box;
  margin-top: 8px;
  padding: 8px;
  background: rgba(139, 216, 255, 0.05);
  border: 1px solid rgba(139, 216, 255, 0.13);
  border-radius: 10px;
}}

.mk-kanji-card:first-child {{
  margin-top: 0;
}}

.mk-kanji-glyph {{
  flex: 0 0 48px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: {WORD_COLOR};
  background: rgba(139, 216, 255, 0.07);
  border-radius: 9px;
  font-size: {KANJI_GLYPH_FONT_SIZE}px;
  line-height: 1;
  font-weight: 500;
}}

.mk-kanji-body {{
  min-width: 0;
  flex: 1;
  line-height: 1.34;
}}

.mk-kanji-reading {{
  color: {READING_COLOR};
  font-size: {READING_FONT_SIZE}px;
  font-weight: 700;
}}

.mk-kanji-meanings {{
  color: {DEFINITION_COLOR};
  font-size: {DEFINITION_FONT_SIZE}px;
}}

.mk-kanji-detail {{
  margin-top: 2px;
  color: {MUTED_COLOR};
  font-size: {DETAIL_FONT_SIZE}px;
}}

.mk-kanji-example-word,
.mk-component-char {{
  color: {WORD_COLOR};
  font-weight: 700;
}}

.mk-kanji-example-reading {{
  color: {READING_COLOR};
}}
""".strip()
