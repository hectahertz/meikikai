# MeikiKai design system

MeikiKai is a macOS menu bar utility for reading Japanese text from the screen. Design serves the task: fast lookup, low distraction, and enough polish that permission and setup flows feel trustworthy.

## Scene

A reader is watching Japanese media or a visual novel on a Mac, often in a dim room, and glances at MeikiKai only long enough to understand a word or complete setup.

## Direction

- Native macOS utility, custom enough to support dark overlays.
- Dark only for now.
- Restrained color: tinted neutrals plus macOS blue for primary action and focus.
- Compact but not cramped. Dialogs should feel calm and predictable.
- The dictionary popup may stay denser than dialogs because it is a transient reading aid.

## Implementation

Shared dialog styling lives in:

- `src/meikikai/gui/design/tokens.py`: colors, typography, radii, spacing.
- `src/meikikai/gui/design/styles.py`: generated QSS for dialogs.
- `src/meikikai/gui/design/widgets.py`: small helpers for titles, separators, panels, and button variants.

Popup styling lives separately in:

- `src/meikikai/gui/popup_design/tokens.py`: popup content colors, type scale, density, truncation limits, width, and insets.
- `src/meikikai/gui/popup_design/styles.py`: generated QSS helpers for popup frame, labels, separators, and kanji cards.
- `scripts/render_popup_sample.py`: popup-only review renderer and contact sheet generator.

Qt style sheets do not support CSS variables or OKLCH, so token values are stored as QSS-compatible RGB and rgba strings. When changing color direction, choose colors in OKLCH first, then convert the final values to Qt-compatible strings.

## Tokens

### Typography

- UI family: SF Pro Text, then common macOS and Japanese fallbacks.
- Base size: 13 px.
- Dialog title: 20 px, 750 weight.
- Body: 12 px, brighter than helper text for setup and confirmation copy.
- Section labels and helper text: 11 px. Section labels are muted so setting titles carry the local hierarchy.
- Avoid display fonts in controls, labels, settings, and status text.

### Color roles

- Window: dark neutral surface.
- Panel: faint raised neutral layer with a low-contrast border.
- Text: strong, default, body, muted, subtle, disabled.
- Accent: macOS blue for primary actions, focus, keycaps, and progress.
- Semantic: success, warning, destructive.

Do not use pure `#000` or `#fff`. Use tinted near-black and near-white values.

### Shape and spacing

- Dialog margin: 18 px horizontal, 20 px vertical.
- Panel radius: 12 px.
- Inset panel radius: 10 px.
- Control radius: 7 px.
- Setting row padding: 14 px horizontal, 9 px vertical.
- Setting row gap: 18 px.
- Title-to-content gap: 14 px.
- Prose block gap: 8 px.
- Prose-to-panel gap: 12 px.
- Footer/action separation: 18 px above action rows.
- Section gap: 16 px. Section label-to-panel gap: 8 px.
- Inset panel padding: 12 px horizontal and vertical.
- Status and detail panels use a faint inset fill with a near-zero border; avoid hard boxed contrast in setup and confirmation flows.

## Components

### Dialogs

Call `apply_dialog_style(self)` in each dialog constructor. Use object names from the shared stylesheet rather than local QSS blocks.

Common object names:

- `dialogTitle`
- `dialogBody`, `bodyText`, `confirmBody`, `messageBody`
- `settingsPanel`, `statusPanel`, `detailsPanel`
- `rowSeparator`
- `settingTitle`, `settingDescription`
- `statusBadgeReady`, `statusBadgeWarning`
- `progressText`, `detailTitle`, `detailText`, `pathText`, `messageDetail`

### Buttons

Use `set_button_variant(button, variant)`:

- `primary`: main action only.
- `destructive`: removal, quit, or irreversible actions.
- `tertiary`: link-style supporting action, such as notices or documentation.
- `None`: default secondary button.

Primary actions should be sparse. Settings should have one primary action, Save. Inline management actions stay secondary unless they complete the current dialog's main task. In a maintenance flow, reinstall/update and uninstall sit in the same action row, while notices move to a tertiary link. Single dismiss actions such as OK should normally stay secondary. Action rows use the shared 8 px gap between buttons. Do not put separator lines above footer buttons; use the shared footer gap instead.

### Panels

Use panels for grouped settings, component status, and install details. Settings panels may keep a clearer grouped outline; status and detail panels should feel quieter, using subtle inset fill and subdued key labels so the value text scans first. Avoid nested panels unless the inner panel carries a different information type.

### Badges

Badges are short state labels only, such as Ready, Reload, Missing. They should not replace explanatory body text.

## Popup content system

The popup has different constraints from dialogs: cursor anchoring, Japanese typography, and dense dictionary content. Keep it separate from the dialog package. Share product-level direction only: dark macOS utility, restrained color, native-ish typography, low distraction.

### Scene and density

The reader is looking away from the popup most of the time, then glances for one or two seconds while media or a visual novel is paused. The popup may be denser than dialogs, but it should still scan in this order:

1. expression and reading,
2. part-of-speech, frequency, and inflection context,
3. glosses,
4. kanji support card.

### Popup tokens

- Width: 496 px. This keeps long English glosses readable without covering too much screen content.
- Inset: 12 px horizontal, 10 px top, 14 px bottom.
- Surface: tinted near-black with 246 alpha and a quiet 1 px outline. Do not use pure black.
- Accent vocabulary: cyan for written forms and glyphs, green for readings, warm muted gold for deconjugation. Accent is semantic, not decoration.
- Text: definitions are near-white; metadata and sense numbers are muted so the word and glosses remain primary.
- Detail accents: kanji examples and components use quieter cyan/green variants than primary expression and reading text.
- Type: Hiragino Sans as the popup base family, with SF Pro Text and common Japanese fallbacks in QSS.
- Scale: 21 px expression, 13 px vocabulary readings, 14 px kanji-card readings, 12 px definitions, 11 px metadata, 10 px kanji details.
- Shape: 16 px popup radius, 10 px kanji card radius, 9 px kanji glyph well radius, 48 px square kanji glyph well.

### Content policies

- Show up to 3 vocabulary entries, 3 senses per entry, and 4 glosses per sense.
- Omitted content uses a quiet footer such as `+ 2 more entries · 2 more senses · 2 more glosses`.
- Use thin separators only between vocabulary entries. Kanji support uses a distinct inset card because it changes information type.
- Place omitted-content footers directly after the visible vocabulary block, before kanji support cards.
- Show kanji support cards only when the character belongs to the original lookup text or a visible vocabulary entry, so cards do not appear attached to omitted entries.
- Use hanging indents for numbered senses so wrapped gloss lines align with the definition text, not the number.
- Treat kanji `ex` and `parts` as a compact detail group: fixed label column, hanging wrapped detail text, clearer top gap after meanings, tight leading, and only a small gap between detail rows.
- Keep kanji examples inline and compact. Avoid nested cards or dialog-style settings panels in popup content.
- Review visual changes with `QT_QPA_PLATFORM=cocoa .venv/bin/python scripts/render_popup_sample.py all`; generated popup review artifacts are ignored by git.
