"""Generated Qt style sheets for the popup design system."""

from meikikai.gui.popup_design.tokens import POPUP, PopupTokens


def transparent_stylesheet() -> str:
    return "background: transparent; border: none;"


def popup_frame_stylesheet(tokens: PopupTokens = POPUP) -> str:
    return f"""
        QFrame#popupFrame {{
            background-color: {tokens.surface_bg};
            color: {tokens.text};
            border-radius: {tokens.surface_radius}px;
            border: 1px solid {tokens.surface_border};
        }}
    """


def plain_label_stylesheet(color: str, tokens: PopupTokens = POPUP, font_stack: str | None = None, italic: bool = False) -> str:
    return (
        f"color: {color}; background: transparent; border: none; "
        f"font-family: {font_stack or tokens.font_stack_qss};"
        f"{' font-style: italic;' if italic else ''}"
    )


def rich_label_stylesheet(
    color: str,
    size: int,
    tokens: PopupTokens = POPUP,
    font_stack: str | None = None,
    italic: bool = False,
) -> str:
    return (
        f"color: {color}; background: transparent; border: none; "
        f"font-family: {font_stack or tokens.font_stack_qss}; font-size: {size}px;"
        f"{' font-style: italic;' if italic else ''}"
    )


def separator_stylesheet(tokens: PopupTokens = POPUP) -> str:
    return f"background-color: {tokens.separator}; border: none;"


def kanji_card_stylesheet(tokens: PopupTokens = POPUP) -> str:
    rule = f"border-left: 2px solid {tokens.kanji_card_rule};" if tokens.kanji_card_rule else ""
    return f"""
        QFrame#kanjiCard {{
            background-color: {tokens.kanji_card_bg};
            border: 1px solid {tokens.kanji_card_border};
            border-radius: {tokens.kanji_card_radius}px;
            {rule}
        }}
    """


def kanji_glyph_stylesheet(tokens: PopupTokens = POPUP) -> str:
    return (
        f"background-color: {tokens.kanji_glyph_bg}; border: none; "
        f"border-radius: {tokens.kanji_glyph_radius}px;"
    )
