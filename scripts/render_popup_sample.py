#!/usr/bin/env python3
"""Render MeikiKai popup sample states and a contact sheet for UI review."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

if sys.platform == "darwin":
    os.environ.setdefault("QT_QPA_PLATFORM", "cocoa")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from meikikai.dictionary.lookup import DictionaryEntry, KanjiEntry  # noqa: E402
from meikikai.gui.popup import Popup  # noqa: E402

OUTPUT_DIR = ROOT / "design" / "popup-screenshots"
CONTACT_SHEET = ROOT / "design" / "popup-contact-sheet.png"


class DummyLock:
    def acquire(self):
        pass

    def release(self):
        pass


class DummyState:
    screen_lock = DummyLock()


@dataclass(frozen=True)
class PopupSample:
    key: str
    name: str
    factory: Callable[[], list[DictionaryEntry | KanjiEntry]]


def vocab(
    written_form: str,
    reading: str,
    glosses: list[str],
    pos: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    freq: int = 999_999,
    deconj: tuple[str, ...] = (),
) -> DictionaryEntry:
    return DictionaryEntry(
        id=1,
        written_form=written_form,
        reading=reading,
        senses=[{"glosses": glosses, "pos": list(pos), "tags": list(tags)}],
        freq=freq,
        deconjugation_process=deconj,
    )


def mockup_entries() -> list[DictionaryEntry | KanjiEntry]:
    return [
        DictionaryEntry(
            id=1,
            written_form="誘う",
            reading="さそう",
            senses=[
                {
                    "glosses": [
                        "to invite",
                        "to ask (someone to do)",
                        "to call (for)",
                        "to take (someone) along",
                    ],
                    "pos": ["v5u", "vt"],
                    "tags": [],
                },
                {
                    "glosses": ["to tempt", "to lure", "to entice", "to seduce"],
                    "pos": ["v5u", "vt"],
                    "tags": [],
                },
                {
                    "glosses": [
                        "to induce (tears, laughter, sleepiness, etc.)",
                        "to arouse (e.g. sympathy)",
                        "to provoke",
                    ],
                    "pos": ["v5u", "vt"],
                    "tags": [],
                },
            ],
            freq=832,
            deconjugation_process=("誘われる", "passive", "('a' stem)"),
        ),
        DictionaryEntry(
            id=2,
            written_form="誘う",
            reading="いざなう",
            senses=[
                {
                    "glosses": [
                        "to invite",
                        "to ask (someone to do)",
                        "to call (for)",
                        "to take (someone) along",
                    ],
                    "pos": ["v5u"],
                    "tags": [],
                },
                {
                    "glosses": ["to tempt", "to lure", "to entice", "to seduce"],
                    "pos": ["v5u"],
                    "tags": [],
                },
            ],
            freq=999_999,
            deconjugation_process=(),
        ),
        KanjiEntry(
            character="誘",
            meanings=["entice", "lead", "tempt", "invite", "ask", "call for"],
            readings=["ユウ", "さそ.う", "いざな.う"],
            examples=[
                {"w": "誘う", "r": "さそう", "m": "to invite"},
                {"w": "誘い", "r": "さそい", "m": "invitation"},
                {"w": "誘導", "r": "ゆうどう", "m": "guidance"},
            ],
            components=[{"c": "言", "m": "say"}, {"c": "秀", "m": "excel"}],
        ),
    ]


def long_entries() -> list[DictionaryEntry]:
    return [
        vocab(
            "取り戻させられなかった",
            "とりもどさせられなかった",
            [
                "to take back",
                "to regain",
                "to recover something that was lost",
                "to restore something to a previous state",
                "to make someone recover",
                "to be unable to cause someone to take something back",
            ],
            pos=("v5s", "vt"),
            tags=("usually written using kana alone", "transitive verb", "long sample tag"),
            freq=12345,
            deconj=(
                "取り戻させられなかった",
                "negative",
                "past",
                "potential",
                "causative",
                "passive",
                "('a' stem)",
            ),
        )
    ]


def nature_entries() -> list[DictionaryEntry | KanjiEntry]:
    return [
        DictionaryEntry(
            id=20,
            written_form="自然",
            reading="しぜん",
            senses=[
                {
                    "glosses": ["nature", "spontaneity", "naturally", "in due course"],
                    "pos": ["n", "adj-no", "adv"],
                    "tags": [],
                },
            ],
            freq=724,
            deconjugation_process=(),
        ),
        KanjiEntry(
            character="自",
            meanings=["oneself", "self", "from"],
            readings=["ジ", "シ", "みずか.ら", "おの.ずから"],
            examples=[
                {"w": "自分", "r": "じぶん", "m": "oneself"},
                {"w": "自然", "r": "しぜん", "m": "nature"},
                {"w": "自由", "r": "じゆう", "m": "freedom"},
            ],
            components=[{"c": "目", "m": "eye"}],
        ),
        KanjiEntry(
            character="然",
            meanings=["so", "if so", "in that case", "well"],
            readings=["ゼン", "ネン", "しか", "しか.り"],
            examples=[
                {"w": "自然", "r": "しぜん", "m": "nature"},
                {"w": "当然", "r": "とうぜん", "m": "natural; obvious"},
                {"w": "全然", "r": "ぜんぜん", "m": "not at all"},
            ],
            components=[{"c": "灬", "m": "fire"}, {"c": "月", "m": "moon; flesh"}, {"c": "犬", "m": "dog"}],
        ),
    ]


def tall_entries() -> list[DictionaryEntry | KanjiEntry]:
    return [
        DictionaryEntry(
            id=10,
            written_form="か",
            reading="か",
            senses=[
                {"glosses": ["question particle", "indicates a question", "marks doubt", "used at sentence end", "whether"], "pos": ["prt"], "tags": []},
                {"glosses": ["or", "alternatively", "some", "one of"], "pos": ["prt"], "tags": []},
                {"glosses": ["indicates uncertainty", "maybe", "perhaps", "I wonder"], "pos": ["prt"], "tags": []},
                {"glosses": ["emphasis", "surprise", "disbelief"], "pos": ["prt"], "tags": []},
                {"glosses": ["archaic exclamation", "poetic ending"], "pos": ["prt"], "tags": ["archaism"]},
            ],
            freq=42,
            deconjugation_process=(),
        ),
        vocab("蚊", "か", ["mosquito"], pos=("n",), freq=6400),
        vocab("課", "か", ["lesson", "section", "department", "division", "counter for lessons"], pos=("n",), freq=7100),
        vocab("可", "か", ["passable", "acceptable", "permitted", "approval"], pos=("n",), freq=12200),
        vocab("化", "か", ["-ization", "action of making something", "change into", "influence"], pos=("suf",), freq=2300),
        KanjiEntry(
            character="可",
            meanings=["can", "passable", "mustn't", "should not", "do not"],
            readings=["カ", "べ.き", "べ.し"],
            examples=[
                {"w": "可能", "r": "かのう", "m": "possible"},
                {"w": "許可", "r": "きょか", "m": "permission"},
                {"w": "可愛い", "r": "かわいい", "m": "cute"},
            ],
            components=[{"c": "口", "m": "mouth"}, {"c": "丁", "m": "street"}],
        ),
    ]


def samples() -> list[PopupSample]:
    return [
        PopupSample("mockup", "01-vocab-deconjugation-kanji", mockup_entries),
        PopupSample("long", "02-long-inflection", long_entries),
        PopupSample("nature", "03-multiple-kanji", nature_entries),
        PopupSample("tall", "04-omitted-results", tall_entries),
    ]


def _popup_for_entries(app: QApplication, entries: list[DictionaryEntry | KanjiEntry]) -> Popup:
    popup = Popup(DummyState())
    popup.timer.stop()
    popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    popup._set_entries(entries)
    app.processEvents()
    return popup


def _cleanup_popup(app: QApplication, popup: Popup) -> None:
    popup.timer.stop()
    popup.close()
    popup.deleteLater()
    app.processEvents()


def render(entries: list[DictionaryEntry | KanjiEntry], output: Path) -> tuple[int, int]:
    app = QApplication.instance() or QApplication([])
    popup = _popup_for_entries(app, entries)
    image = popup.grab()
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output))
    size = popup.size()
    _cleanup_popup(app, popup)
    return size.width(), size.height()


def render_sample(app: QApplication, sample: PopupSample, output_dir: Path) -> Path:
    popup = _popup_for_entries(app, sample.factory())
    image = popup.grab()
    output = output_dir / f"{sample.name}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output))
    _cleanup_popup(app, popup)
    return output


def render_switch(output: Path) -> tuple[int, int]:
    app = QApplication.instance() or QApplication([])
    popup = Popup(DummyState())
    popup.timer.stop()
    popup.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    for entries in (mockup_entries(), long_entries(), mockup_entries(), long_entries()):
        popup._set_entries(entries)
        app.processEvents()
    image = popup.grab()
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output))
    size = popup.size()
    _cleanup_popup(app, popup)
    return size.width(), size.height()


def _font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def make_contact_sheet(images: list[Path], output: Path, columns: int = 2) -> None:
    loaded = [(path, Image.open(path).convert("RGBA")) for path in images]
    if not loaded:
        raise RuntimeError("No popup screenshots were rendered.")

    label_font = _font(14, bold=True)
    meta_font = _font(11)
    tile_bg = (32, 33, 39, 255)
    page_bg = tile_bg
    text = (238, 242, 247, 255)
    muted = (170, 179, 194, 255)

    gutter = 18
    margin = 20
    label_h = 34
    inner_pad = 10
    tile_sizes = [(image.width + inner_pad * 2, image.height + inner_pad * 2) for _, image in loaded]
    column_count = min(columns, len(loaded))
    columns_data: list[list[tuple[int, Path, Image.Image, tuple[int, int]]]] = [[] for _ in range(column_count)]
    column_heights = [0] * column_count

    for index, ((path, image), tile_size) in enumerate(zip(loaded, tile_sizes)):
        column = min(range(column_count), key=lambda col: column_heights[col])
        columns_data[column].append((index, path, image, tile_size))
        column_heights[column] += label_h + tile_size[1] + gutter

    column_widths = [
        max((tile_size[0] for _, _, _, tile_size in column), default=0)
        for column in columns_data
    ]
    sheet_w = margin * 2 + sum(column_widths) + gutter * (column_count - 1)
    sheet_h = margin * 2 + max(column_heights) - gutter

    sheet = Image.new("RGBA", (sheet_w, sheet_h), page_bg)
    draw = ImageDraw.Draw(sheet)

    x = margin
    for column_width, column in zip(column_widths, columns_data):
        y = margin
        for index, path, image, tile_size in column:
            tile_x = x + (column_width - tile_size[0]) // 2
            label = path.stem.removeprefix(f"{index + 1:02d}-").replace("-", " ").title()
            draw.text((tile_x, y), label, fill=text, font=label_font)
            draw.text((tile_x, y + 16), f"{image.width} × {image.height}px", fill=muted, font=meta_font)

            tile_y = y + label_h
            draw.rectangle((tile_x, tile_y, tile_x + tile_size[0], tile_y + tile_size[1]), fill=tile_bg)
            image_x = tile_x + inner_pad
            image_y = tile_y + inner_pad
            sheet.alpha_composite(image, (image_x, image_y))
            y += label_h + tile_size[1] + gutter
        x += column_width + gutter

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(output)


def render_all(output_dir: Path, contact_sheet: Path, columns: int) -> list[Path]:
    app = QApplication.instance() or QApplication([])
    rendered = [render_sample(app, sample, output_dir) for sample in samples()]
    make_contact_sheet(rendered, contact_sheet, columns=columns)
    return rendered


def _sample_by_key(key: str) -> PopupSample:
    for sample in samples():
        if sample.key == key:
            return sample
    raise KeyError(key)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render MeikiKai popup review PNGs.")
    parser.add_argument(
        "case",
        nargs="?",
        choices=("all", "mockup", "long", "switch", "tall", "nature"),
        default="all",
        help="Sample state to render. Default: all review states and a contact sheet.",
    )
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output PNG path for single-case renders.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Output directory for all popup samples.")
    parser.add_argument("--contact-sheet", type=Path, default=CONTACT_SHEET, help="Output contact sheet path for all samples.")
    parser.add_argument("--columns", type=int, default=2, help="Contact sheet column count.")
    args = parser.parse_args()

    if args.case == "all":
        rendered = render_all(args.output_dir, args.contact_sheet, columns=args.columns)
        for image in rendered:
            print(image.relative_to(ROOT))
        print(args.contact_sheet.relative_to(ROOT))
        return 0

    output = args.output or Path(f"/tmp/meikikai_popup_{args.case}.png")
    if args.case == "switch":
        width, height = render_switch(output)
    else:
        sample = _sample_by_key(args.case)
        width, height = render(sample.factory(), output)

    print(f"Rendered {args.case} popup to {output} ({width}x{height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
