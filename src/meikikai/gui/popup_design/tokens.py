"""Popup-specific design tokens for MeikiKai's dictionary overlay.

The popup is a transient reading aid with different constraints from dialogs:
cursor anchoring, dense Japanese dictionary content, and quick visual parsing.
Keep these tokens separate from ``meikikai.gui.design`` dialog tokens.
"""

from dataclasses import dataclass, replace

Rgb = tuple[int, int, int]


def rgba(rgb: Rgb, alpha: int) -> str:
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"


@dataclass(frozen=True)
class PopupLayoutTier:
    width: int
    content_margin_left: int
    content_margin_top: int
    content_margin_right: int
    content_margin_bottom: int
    show_metadata: bool
    show_deconjugation: bool
    kanji_presentation: str

    @property
    def content_width(self) -> int:
        # Subtract the frame border so fixed-width content does not fight the 1 px outline.
        return self.width - self.content_margin_left - self.content_margin_right - 2


@dataclass(frozen=True)
class PopupTokens:
    font_family: str = "Hiragino Sans"
    font_stack_qss: str = '"SF Pro Text", "Helvetica Neue", "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif'
    jp_font_family: str = "Hiragino Sans"
    jp_font_stack_qss: str = '"SF Pro Text", "Helvetica Neue", "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif'
    gloss_font_family: str = "Hiragino Sans"
    gloss_font_stack_qss: str = '"SF Pro Text", "Helvetica Neue", "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif'
    gloss_italic: bool = False
    word_font_weight: int = 600
    sense_number_weight: int = 600
    kanji_reading_weight: int = 700
    reading_brackets: bool = True
    uppercase_labels: bool = False
    separator_width: int = 0

    width: int = 496
    shadow_margin: int = 0
    content_margin_left: int = 12
    content_margin_top: int = 10
    content_margin_right: int = 12
    content_margin_bottom: int = 14

    surface_bg: str = "rgba(24, 27, 36, 246)"
    surface_border: str = "rgba(237, 241, 247, 34)"
    text: str = "#edf1f7"
    definition_text: str = "#eef2f8"
    muted_text: str = "#a8b0c2"
    word_text: str = "#8bd8ff"
    reading_text: str = "#8ed99e"
    separator: str = "rgba(237, 241, 247, 22)"
    metadata_text: str = "#929cae"
    metadata_label_text: str = "#808b9f"
    detail_label_text: str = ""
    omission_text: str = "#858fa3"
    deconjugation_text: str = "#c6b57f"
    deconjugation_detail_text: str = ""
    sense_number_text: str = "#8b96aa"
    detail_word_text: str = "#79c9ee"
    detail_reading_text: str = "#82c78f"

    kanji_card_bg: str = "rgba(139, 216, 255, 12)"
    kanji_card_border: str = "rgba(237, 241, 247, 24)"
    kanji_card_rule: str = ""
    kanji_glyph_bg: str = "rgba(139, 216, 255, 18)"

    surface_radius: int = 16
    kanji_card_radius: int = 10
    kanji_glyph_radius: int = 9

    word_font_size: int = 21
    kanji_glyph_font_size: int = 34
    reading_font_size: int = 13
    kanji_reading_font_size: int = 14
    definition_font_size: int = 12
    metadata_font_size: int = 11
    detail_font_size: int = 10

    entry_meta_gap: int = 1
    entry_deconjugation_gap: int = 2
    entry_definition_gap: int = 5
    entry_definition_gap_without_meta: int = 3
    kanji_before_gap: int = 8
    footer_before_gap: int = 7
    definition_number_width: int = 14
    definition_number_gap: int = 5
    definition_row_gap: int = 1
    kanji_body_row_gap: int = 2
    kanji_detail_top_gap: int = 4
    kanji_detail_row_gap: int = 7
    kanji_detail_label_width: int = 29
    kanji_detail_label_gap: int = 4
    kanji_detail_line_height_percent: int = 100

    max_senses_per_entry: int = 3
    max_glosses_per_sense: int = 4

    compact_width: int = 344
    standard_width: int = 420

    @property
    def content_width(self) -> int:
        # Subtract the frame border so fixed-width content does not fight the 1 px outline.
        return self.width - self.content_margin_left - self.content_margin_right - 2

    def layout_tier(self, layout: str) -> PopupLayoutTier:
        if layout == "compact":
            return PopupLayoutTier(
                width=self.compact_width,
                content_margin_left=10,
                content_margin_top=9,
                content_margin_right=10,
                content_margin_bottom=11,
                show_metadata=False,
                show_deconjugation=False,
                kanji_presentation="chip",
            )
        if layout == "standard":
            return PopupLayoutTier(
                width=self.standard_width,
                content_margin_left=11,
                content_margin_top=10,
                content_margin_right=11,
                content_margin_bottom=13,
                show_metadata=True,
                show_deconjugation=True,
                kanji_presentation="compact",
            )
        return PopupLayoutTier(
            width=self.width,
            content_margin_left=self.content_margin_left,
            content_margin_top=self.content_margin_top,
            content_margin_right=self.content_margin_right,
            content_margin_bottom=self.content_margin_bottom,
            show_metadata=True,
            show_deconjugation=True,
            kanji_presentation="full",
        )


POPUP_THEME_LABELS = {
    "paper": "Paper",
    "nazeka": "Nazeka",
    "nord": "Nord",
    "catppuccin": "Catppuccin",
    "kanagawa_wave": "Kanagawa Wave",
}
POPUP_THEME_OPTIONS = tuple(POPUP_THEME_LABELS)
DEFAULT_POPUP_THEME = "paper"

_BASE_POPUP = PopupTokens()

# Palette inspirations:
# - Nazeka: Meikipop's original/default theme, adapted to MeikiKai's denser popup system.
# - Nord: Polar Night neutrals, Frost cyan-blue, Aurora green and yellow.
# - Catppuccin Mocha: base/mantle neutrals with sky, green, mauve, and yellow accents.
# - Kanagawa Wave: sumi ink neutrals with crystal blue, spring green, carp yellow, and wave aqua.
_PAPER_POPUP = replace(
    _BASE_POPUP,
    jp_font_family="Hiragino Mincho ProN",
    jp_font_stack_qss='"Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif',
    gloss_font_family="Iowan Old Style",
    gloss_font_stack_qss='"Iowan Old Style", "Palatino", Georgia, "Hiragino Mincho ProN", serif',
    gloss_italic=False,
    word_font_weight=500,
    sense_number_weight=400,
    kanji_reading_weight=400,
    kanji_detail_label_width=40,
    reading_brackets=False,
    uppercase_labels=True,
    separator_width=40,
    surface_radius=0,
    kanji_card_radius=0,
    kanji_glyph_radius=0,
    word_font_size=24,
    definition_font_size=14,
    surface_bg="#f5f1ea",
    surface_border="#e2d9cc",
    text="#1f1c18",
    definition_text="#1f1c18",
    muted_text="#8a8175",
    word_text="#1f1c18",
    reading_text="#8a8175",
    separator="#e2d9cc",
    metadata_text="#8a8175",
    metadata_label_text="#8a8175",
    omission_text="#8a8175",
    deconjugation_text="#b8391f",
    deconjugation_detail_text="#8a8175",
    sense_number_text="#b8391f",
    detail_label_text="#b8391f",
    detail_word_text="#1f1c18",
    detail_reading_text="#8a8175",
    kanji_card_bg="transparent",
    kanji_card_border="transparent",
    kanji_card_rule="#b8391f",
    kanji_glyph_bg="transparent",
)

PAPER_THEME_VARIANTS = {
    "light": _PAPER_POPUP,
    "dark": replace(
        _PAPER_POPUP,
        surface_bg="#191816",
        surface_border="#34312c",
        text="#ece6da",
        definition_text="#ece6da",
        muted_text="#9b9385",
        word_text="#ece6da",
        reading_text="#9b9385",
        separator="#34312c",
        metadata_text="#9b9385",
        metadata_label_text="#9b9385",
        omission_text="#9b9385",
        deconjugation_text="#e0735a",
        deconjugation_detail_text="#9b9385",
        sense_number_text="#e0735a",
        detail_label_text="#e0735a",
        detail_word_text="#ece6da",
        detail_reading_text="#9b9385",
        kanji_card_rule="#e0735a",
    ),
}

POPUP_THEMES: dict[str, PopupTokens] = {
    "paper": _PAPER_POPUP,
    "nazeka": _BASE_POPUP,
    "nord": replace(
        _BASE_POPUP,
        surface_bg=rgba((46, 52, 64), 246),
        surface_border=rgba((216, 222, 233), 31),
        text="#eceff4",
        definition_text="#eceff4",
        muted_text="#a8b1c2",
        word_text="#88c0d0",
        reading_text="#8fbcbb",
        separator=rgba((216, 222, 233), 18),
        metadata_text="#a8b1c2",
        metadata_label_text="#8794a8",
        omission_text="#94a0b5",
        deconjugation_text="#b8ad8a",
        sense_number_text="#81a1c1",
        detail_word_text="#88c0d0",
        detail_reading_text="#8fbcbb",
        kanji_card_bg=rgba((136, 192, 208), 16),
        kanji_card_border=rgba((216, 222, 233), 20),
        kanji_glyph_bg=rgba((136, 192, 208), 23),
    ),
    "catppuccin": replace(
        _BASE_POPUP,
        surface_bg=rgba((30, 30, 46), 246),
        surface_border=rgba((205, 214, 244), 32),
        text="#cdd6f4",
        definition_text="#d7def8",
        muted_text="#a6adc8",
        word_text="#89dceb",
        reading_text="#a6e3a1",
        separator=rgba((205, 214, 244), 20),
        metadata_text="#a6adc8",
        metadata_label_text="#7f849c",
        omission_text="#8c93ad",
        deconjugation_text="#b8ac91",
        sense_number_text="#b4befe",
        detail_word_text="#89dceb",
        detail_reading_text="#a6e3a1",
        kanji_card_bg=rgba((137, 220, 235), 16),
        kanji_card_border=rgba((205, 214, 244), 18),
        kanji_glyph_bg=rgba((137, 220, 235), 23),
    ),
    "kanagawa_wave": replace(
        _BASE_POPUP,
        surface_bg=rgba((31, 31, 40), 246),
        surface_border=rgba((220, 215, 186), 30),
        text="#dcd7ba",
        definition_text="#e0dcc4",
        muted_text="#a6a69c",
        word_text="#8ba4e0",
        reading_text="#98bb6c",
        separator=rgba((220, 215, 186), 16),
        metadata_text="#a6a69c",
        metadata_label_text="#7e8294",
        omission_text="#8c8a82",
        deconjugation_text="#b3a27a",
        sense_number_text="#7aa89f",
        detail_word_text="#8ba4e0",
        detail_reading_text="#98bb6c",
        kanji_card_bg=rgba((139, 164, 224), 15),
        kanji_card_border=rgba((220, 215, 186), 18),
        kanji_glyph_bg=rgba((139, 164, 224), 22),
    ),
}


def popup_tokens(theme: str | None = None, appearance: str | None = None) -> PopupTokens:
    theme = theme or DEFAULT_POPUP_THEME
    if theme == "paper":
        return PAPER_THEME_VARIANTS.get(appearance or system_appearance(), PAPER_THEME_VARIANTS["light"])
    return POPUP_THEMES.get(theme, POPUP_THEMES[DEFAULT_POPUP_THEME])


def system_appearance() -> str:
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QGuiApplication

        if QGuiApplication.instance() and QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return "dark"
    except Exception:
        pass
    return "light"


def popup_theme_label(theme: str) -> str:
    return POPUP_THEME_LABELS.get(theme, POPUP_THEME_LABELS[DEFAULT_POPUP_THEME])


POPUP = popup_tokens(DEFAULT_POPUP_THEME)
