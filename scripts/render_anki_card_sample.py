#!/usr/bin/env python3
"""Render MeikiKai Anki card sample states to PNG files for UI review."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meikikai.anki.cards import BACK_TEMPLATE, CARD_CSS, FRONT_TEMPLATE, build_vocab_card_payload  # noqa: E402
from meikikai.dictionary.lookup import DictionaryEntry, LookupResult  # noqa: E402
from meikikai.ocr.interface import LookupContext  # noqa: E402
from render_popup_sample import long_entries, mockup_entries, nature_entries, tall_entries  # noqa: E402

BROWSER_PATHS = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
]

SECTION_RE = re.compile(r"{{([#^])([A-Za-z0-9_]+)}}(.*?){{/\2}}", re.DOTALL)
VARIABLE_RE = re.compile(r"{{([A-Za-z0-9_]+)}}")

SAMPLES = {
    "mockup": (
        mockup_entries,
        "まるで見えない手に誘われるように、彼女は森の奥へ進んだ。",
        "誘われる",
    ),
    "long": (
        long_entries,
        "失った記憶を取り戻させられなかったことだけが、今も胸に残っている。",
        "取り戻させられなかった",
    ),
    "nature": (
        nature_entries,
        "静かな自然の中で、二人はしばらく言葉を忘れていた。",
        "自然",
    ),
    "tall": (
        tall_entries,
        "本当に行くか、まだ決めていない。",
        "か",
    ),
}


def first_dictionary_entry(entries: Iterable) -> DictionaryEntry:
    for entry in entries:
        if isinstance(entry, DictionaryEntry):
            return entry
    raise RuntimeError("Sample does not contain a dictionary entry.")


def sample_lookup_result(case: str) -> LookupResult:
    entries_factory, sentence, matched_text = SAMPLES[case]
    entries = entries_factory()
    hit_index = sentence.index(matched_text)
    entry = first_dictionary_entry(entries)
    entry.match_len = len(matched_text)
    entry.matched_text = matched_text

    context = LookupContext(
        lookup_text=sentence[hit_index:],
        full_text=sentence,
        hit_index=hit_index,
        is_vertical=False,
    )
    return LookupResult(entries=entries, context=context, lookup_text=context.lookup_text)


def render_template(template: str, fields: dict[str, str]) -> str:
    html = template
    while True:
        match = SECTION_RE.search(html)
        if not match:
            break
        marker, field_name, content = match.groups()
        value = fields.get(field_name, "")
        replacement = content if (bool(value) == (marker == "#")) else ""
        html = html[:match.start()] + replacement + html[match.end():]
    return VARIABLE_RE.sub(lambda m: fields.get(m.group(1), ""), html)


def page_html(case: str, side: str) -> str:
    payload = build_vocab_card_payload(sample_lookup_result(case))
    if not payload:
        raise RuntimeError(f"Could not build Anki card payload for case: {case}")

    cards = []
    if side in ("front", "both"):
        cards.append(("Front", render_template(FRONT_TEMPLATE, payload.fields)))
    if side in ("back", "both"):
        cards.append(("Back", render_template(BACK_TEMPLATE, payload.fields)))

    cards_html = "\n".join(
        f'<section class="mk-debug-card-wrap"><div class="mk-debug-label">{label}</div>{card}</section>'
        for label, card in cards
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MeikiKai Anki card sample: {case} {side}</title>
<style>
{CARD_CSS}

html {{
  background: #11131a;
}}

body.card.mk-debug-page {{
  min-height: 100vh;
  box-sizing: border-box;
  margin: 0;
  padding: 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  background: radial-gradient(circle at top, #202636 0, #11131a 58%);
}}

.mk-debug-card-wrap {{
  width: 496px;
}}

.mk-debug-label {{
  box-sizing: border-box;
  width: 496px;
  margin: 0 0 7px;
  padding: 0 4px;
  color: #768195;
  font: 700 11px/1.2 "SF Pro Text", "Helvetica Neue", sans-serif;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}}
</style>
</head>
<body class="card mk-debug-page">
{cards_html}
</body>
</html>
"""


def find_browser(explicit_browser: str | None) -> Path | None:
    if explicit_browser:
        path = Path(explicit_browser).expanduser()
        return path if path.exists() else None
    for path in BROWSER_PATHS:
        if path.exists():
            return path
    return None


def render_png(browser: Path, html_path: Path, output: Path, width: int, height: int, scale: float):
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with tempfile.TemporaryDirectory(prefix="meikikai-card-browser-") as user_data_dir:
        last_error = "Browser screenshot failed."
        for headless_flag in ("--headless=new", "--headless"):
            cmd = [
                str(browser),
                headless_flag,
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-extensions",
                "--disable-sync",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-debugging-port=0",
                f"--user-data-dir={user_data_dir}",
                f"--window-size={width},{height}",
                f"--force-device-scale-factor={scale}",
                f"--screenshot={output}",
                html_path.resolve().as_uri(),
            ]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if output.exists() and output.stat().st_size > 0:
                    _stop_browser(process)
                    return
                if process.poll() is not None:
                    break
                time.sleep(0.1)

            stdout, stderr = process.communicate(timeout=1) if process.poll() is not None else ("", "")
            last_error = (stderr or stdout or last_error).strip()
            _stop_browser(process)

        raise RuntimeError(last_error)


def _stop_browser(process: subprocess.Popen):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a MeikiKai Anki card sample PNG.")
    parser.add_argument(
        "case",
        nargs="?",
        choices=tuple(SAMPLES.keys()),
        default="mockup",
        help="Sample state to render. Default: mockup.",
    )
    parser.add_argument(
        "side",
        nargs="?",
        choices=("front", "back", "both"),
        default="both",
        help="Card side to render. Default: both.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output PNG path. Default: /tmp/meikikai_anki_card_<case>_<side>.png",
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=None,
        help="Output debug HTML path. Default: /tmp/meikikai_anki_card_<case>_<side>.html",
    )
    parser.add_argument(
        "--browser",
        default=None,
        help="Chromium-based browser executable. Default: auto-detect Chrome/Chromium/Edge/Brave.",
    )
    parser.add_argument("--width", type=int, default=560, help="Browser viewport width in CSS pixels.")
    parser.add_argument("--height", type=int, default=1100, help="Browser viewport height in CSS pixels.")
    parser.add_argument("--scale", type=float, default=1.0, help="Browser device scale factor.")
    args = parser.parse_args()

    output = args.output or Path(f"/tmp/meikikai_anki_card_{args.case}_{args.side}.png")
    html_path = args.html or Path(f"/tmp/meikikai_anki_card_{args.case}_{args.side}.html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(page_html(args.case, args.side), encoding="utf-8")

    browser = find_browser(args.browser)
    if not browser:
        print(f"Wrote debug HTML to {html_path}")
        print("No Chromium-based browser was found, so no PNG was rendered.", file=sys.stderr)
        return 2

    render_png(browser, html_path, output, args.width, args.height, args.scale)
    print(f"Rendered {args.case} Anki card {args.side} to {output}")
    print(f"Wrote debug HTML to {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
