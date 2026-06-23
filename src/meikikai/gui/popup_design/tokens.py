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
    omission_text: str = "#858fa3"
    deconjugation_text: str = "#c6b57f"
    sense_number_text: str = "#8b96aa"
    detail_word_text: str = "#79c9ee"
    detail_reading_text: str = "#82c78f"

    kanji_card_bg: str = "rgba(139, 216, 255, 12)"
    kanji_card_border: str = "rgba(237, 241, 247, 24)"
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
    "nazeka": "Nazeka",
    "nord": "Nord",
    "catppuccin": "Catppuccin",
    "kanagawa_wave": "Kanagawa Wave",
}
POPUP_THEME_OPTIONS = tuple(POPUP_THEME_LABELS)
DEFAULT_POPUP_THEME = "nord"

_BASE_POPUP = PopupTokens()

# Palette inspirations:
# - Nazeka: Meikipop's original/default theme, adapted to MeikiKai's denser popup system.
# - Nord: Polar Night neutrals, Frost cyan-blue, Aurora green and yellow.
# - Catppuccin Mocha: base/mantle neutrals with sky, green, mauve, and yellow accents.
# - Kanagawa Wave: sumi ink neutrals with crystal blue, spring green, carp yellow, and wave aqua.
POPUP_THEMES: dict[str, PopupTokens] = {
    "nazeka": _BASE_POPUP,
    "nord": replace(
        _BASE_POPUP,
        surface_bg=rgba((46, 52, 64), 246),
        surface_border=rgba((216, 222, 233), 34),
        text="#eceff4",
        definition_text="#e5e9f0",
        muted_text="#a8b1c2",
        word_text="#88c0d0",
        reading_text="#a3be8c",
        separator=rgba((216, 222, 233), 23),
        metadata_text="#9aa7b8",
        metadata_label_text="#7f8da3",
        omission_text="#8794a8",
        deconjugation_text="#ebcb8b",
        sense_number_text="#81a1c1",
        detail_word_text="#8fbcbb",
        detail_reading_text="#a3be8c",
        kanji_card_bg=rgba((136, 192, 208), 13),
        kanji_card_border=rgba((216, 222, 233), 25),
        kanji_glyph_bg=rgba((136, 192, 208), 19),
    ),
    "catppuccin": replace(
        _BASE_POPUP,
        surface_bg=rgba((30, 30, 46), 246),
        surface_border=rgba((205, 214, 244), 34),
        text="#cdd6f4",
        definition_text="#cdd6f4",
        muted_text="#a6adc8",
        word_text="#89dceb",
        reading_text="#a6e3a1",
        separator=rgba((205, 214, 244), 23),
        metadata_text="#bac2de",
        metadata_label_text="#9399b2",
        omission_text="#9399b2",
        deconjugation_text="#f9e2af",
        sense_number_text="#cba6f7",
        detail_word_text="#74c7ec",
        detail_reading_text="#94e2d5",
        kanji_card_bg=rgba((137, 220, 235), 13),
        kanji_card_border=rgba((205, 214, 244), 25),
        kanji_glyph_bg=rgba((137, 220, 235), 19),
    ),
    "kanagawa_wave": replace(
        _BASE_POPUP,
        surface_bg=rgba((31, 31, 40), 246),
        surface_border=rgba((220, 215, 186), 32),
        text="#dcd7ba",
        definition_text="#dcd7ba",
        muted_text="#a6a69c",
        word_text="#7e9cd8",
        reading_text="#98bb6c",
        separator=rgba((220, 215, 186), 22),
        metadata_text="#a6a69c",
        metadata_label_text="#7e8294",
        omission_text="#8c8a82",
        deconjugation_text="#e6c384",
        sense_number_text="#7aa89f",
        detail_word_text="#7aa89f",
        detail_reading_text="#98bb6c",
        kanji_card_bg=rgba((126, 156, 216), 13),
        kanji_card_border=rgba((220, 215, 186), 24),
        kanji_glyph_bg=rgba((126, 156, 216), 18),
    ),
}


def popup_tokens(theme: str | None = None) -> PopupTokens:
    return POPUP_THEMES.get(theme or DEFAULT_POPUP_THEME, POPUP_THEMES[DEFAULT_POPUP_THEME])


def popup_theme_label(theme: str) -> str:
    return POPUP_THEME_LABELS.get(theme, POPUP_THEME_LABELS[DEFAULT_POPUP_THEME])


POPUP = popup_tokens(DEFAULT_POPUP_THEME)
