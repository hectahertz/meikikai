# MeikiKai

MeikiKai is a macOS Japanese OCR popup dictionary. It watches a selected screen, reads visible Japanese text with OCR, and shows dictionary entries when you hover text with your chosen hotkey.

This project is a fork of [rtr46/meikipop](https://github.com/rtr46/meikipop). Thank you to rtr46 and the MeikiPop contributors for the original app, dictionary pipeline, OCR architecture, and overall reading workflow this fork builds on.

## What changed in this fork

MeikiKai renames the app, Python package, CLI, support files, and build artifacts around the new name, while narrowing the app experience around macOS:

- Renamed the desktop app, package, and command to **MeikiKai** / `meikikai`.
- macOS-only runtime, packaging, paths, permissions, and input handling.
- Removed Windows, Linux, Wayland, Flatpak, Magpie, and Chrome Screen AI support.
- Added separate app and menu bar icons, including an inactive icon when paused.
- Moved the enable/pause toggle into the menu bar menu as the first item.
- Added optional media auto-pause while the popup is open.

## Features

- **Screen-wide lookup:** works with games, manga, videos, PDFs, websites, and other apps because it reads pixels from the selected screen.
- **Display selection:** OCR a full display or all displays.
- **Auto and manual scan modes:** keep OCR results warm in the background, or scan only when pressing the hotkey.
- **Hover popup:** dictionary entries appear next to the cursor, with configurable positioning including a visual-novel-friendly mode.
- **Local and remote OCR providers:** use fast local `meikiocr`, Google Lens, or a local `owocr` websocket server.
- **JMdict/KANJIDIC dictionary:** includes word lookup, deconjugation, frequency ranking, kanji entries, components, and examples.
- **Yomitan imports:** replace the bundled dictionary with one or more Yomitan/Yomichan dictionaries.
- **Customizable appearance:** themes, colors, opacity, font, compact mode, visible fields, and kanji display options.

## Requirements

- macOS
- Python 3.10 or newer if running from source
- macOS permissions for the app or terminal you use to run it:
  - **Screen Recording**
  - **Accessibility**
  - **Input Monitoring**

MeikiKai stores user data in:

- `~/Library/Application Support/meikikai/config.ini`
- `~/Library/Application Support/meikikai/dictionary.pkl`
- `~/Library/Caches/meikikai/`

## Install

### macOS app bundle

Download the latest release from this fork:

- <https://github.com/hectahertz/meikipop/releases/latest>

Unpack it, start `MeikiKai.app`, then grant the macOS permissions listed above when prompted or from System Settings.

### Development setup

```bash
git clone https://github.com/hectahertz/meikipop.git meikikai
cd meikikai
python -m pip install -e .
meikikai
```

## Usage

1. Start MeikiKai with `MeikiKai.app` or `meikikai`.
2. Move the mouse over Japanese text on the selected screen.
3. Hold the configured hotkey when required. The default hotkey is `shift`.
4. Right-click the menu bar icon to enable/pause MeikiKai, open settings, change OCR provider, switch scan mode, choose scan screen, or quit.

In auto scan mode, MeikiKai can show lookups without holding the hotkey if **Show Popup without Hotkey** is enabled.

## OCR providers

### meikiocr (local)

Fast local OCR, especially useful for horizontal Japanese game text. Models are handled by the `meikiocr` package. This is the default configured provider.

### Google Lens (remote)

High-accuracy remote OCR. It requires an internet connection and sends screenshots of the selected screen to Google Lens. Enable Google Lens compression if latency is high on a slow connection.

### owocr (Websocket)

Use any OCR engine supported by [owocr](https://github.com/AuroraWright/owocr/tree/master/owocr) through a local websocket server.

```bash
pip install -U "owocr>=1.15"
owocr -r websocket -w websocket -of json -e glens
```

Then choose **owocr (Websocket)** from the menu bar OCR provider menu or settings dialog.

### Custom providers

Custom OCR providers can be added when running from source. See [docs/CUSTOM_OCR_PROVIDER.md](docs/CUSTOM_OCR_PROVIDER.md).

## Dictionary commands

MeikiKai downloads the default dictionary on first run if `dictionary.pkl` is missing. To rebuild it from source data:

```bash
meikikai build-dict
```

To replace it with Yomitan/Yomichan dictionaries:

```bash
# Preserve supported structured HTML formatting
meikikai import-yomitan-dict-html dict.zip

# Import compact plain-text definitions
meikikai import-yomitan-dict-text dict.zip

# Merge multiple dictionaries into one dictionary.pkl
meikikai import-yomitan-dict-text dict1.zip dict2.zip
```

Imports overwrite `~/Library/Application Support/meikikai/dictionary.pkl`.

## Settings

Open settings from the menu bar icon. Useful options include:

- hotkey and maximum lookup length
- OCR provider and Google Lens compression
- auto scan mode, scan interval, scan-on-mouse-move, and hotkeyless lookup
- popup position mode, compact mode, and media auto-pause
- visible dictionary fields: glosses, deconjugation, part of speech, tags, frequency, kanji entries, examples, and components
- theme, opacity, font, font sizes, and colors

## Building the macOS app

This fork keeps a PyInstaller spec for the macOS bundle:

```bash
pyinstaller meikikai.macos.spec
```

The generated bundle is named `MeikiKai.app`.

## License

MeikiKai inherits MeikiPop's GNU General Public License v3.0 license. See [LICENSE](LICENSE).
