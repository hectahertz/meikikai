"""Popup-specific design tokens for MeikiKai's dictionary overlay.

The popup is a transient reading aid with different constraints from dialogs:
cursor anchoring, dense Japanese dictionary content, and quick visual parsing.
Keep these tokens separate from ``meikikai.gui.design`` dialog tokens.
"""

from dataclasses import dataclass

Rgb = tuple[int, int, int]


def rgba(rgb: Rgb, alpha: int) -> str:
    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"


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

    max_vocab_entries: int = 3
    max_senses_per_entry: int = 3
    max_glosses_per_sense: int = 4

    @property
    def content_width(self) -> int:
        # Subtract the frame border so fixed-width content does not fight the 1 px outline.
        return self.width - self.content_margin_left - self.content_margin_right - 2


POPUP = PopupTokens()
