# MeikiKai

MeikiKai is a macOS Japanese OCR popup dictionary. Hover Japanese text on screen to see dictionary entries.

<img width="496" alt="MeikiKai popup example" src="https://github.com/user-attachments/assets/39b415d8-2ed9-4a57-8b96-e25c96a87bb1">

Forked from [rtr46/meikipop](https://github.com/rtr46/meikipop).

## What changed

### Added

- Native **MeikiKai** naming.
- Dark redesigned popup.
- Cleaner settings.
- App and menu bar icons.
- Menu bar controls.
- Optional media auto-pause.

### Simplified

- macOS-only app flow.
- Always-on OCR for one display or all displays.
- Local OCR with `meikiocr`.
- One bundled popup layout.

## Features

- Works anywhere text is visible: games, manga, videos, PDFs, websites, and more.
- Uses local Japanese OCR.
- Supports JMdict/KANJIDIC lookup, deconjugation, frequency, kanji, and examples.
- Imports Yomitan/Yomichan dictionaries.
- Stays visible across macOS Spaces.

## Requirements

- macOS
- Python 3.10+ when running from source
- macOS permissions: Screen Recording, Accessibility, and Input Monitoring

Data: `~/Library/Application Support/meikikai/`. Caches: `~/Library/Caches/meikikai/`. Logs: `~/Library/Logs/MeikiKai/`.

## Install

Download the latest app bundle:

<https://github.com/hectahertz/meikikai/releases/latest>

Or run from source:

```bash
git clone https://github.com/hectahertz/meikikai.git
cd meikikai
python -m pip install -e .
meikikai
```

## Usage

1. Start `MeikiKai.app` or run `meikikai`.
2. Move the mouse over Japanese text on the selected screen.
3. Use the menu bar icon for pause, media auto-pause, settings, screen selection, and quit.

## Dictionary commands

MeikiKai downloads the default dictionary on first run if needed.

```bash
# Rebuild the default dictionary
meikikai build-dict

# Import Yomitan/Yomichan dictionaries
meikikai import-yomitan-dict-html dict.zip
meikikai import-yomitan-dict-text dict1.zip dict2.zip
```

Imports overwrite `~/Library/Application Support/meikikai/dictionary.pkl`.

## Popup sample

Regenerate the README image with:

```bash
.venv/bin/python scripts/render_popup_sample.py mockup -o /tmp/meikikai_popup_mockup.png
```

## Build the macOS app

```bash
pyinstaller meikikai.macos.spec
```

Build, install, and reopen locally:

```bash
cp .env.example .env
scripts/build_install_macos.sh
```

## License

GPL-3.0. See [LICENSE](LICENSE).
