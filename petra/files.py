"""Reading the bytes of a card or a design file as text. Untrusted: the trusted front end
starts at the text, so a bug here costs an input error or a check of other text, which the
report shows by its path and its lines."""
from __future__ import annotations

import codecs
from pathlib import Path


def card_of(path: str) -> str:
    """The card a design answers when nobody names another: NAME.card beside NAME.petra."""
    return path.removesuffix(".petra") + ".card"


def read_pair(path: str | Path, card: str | Path | None = None) -> tuple[str, str]:
    """The text of the card a design answers, the .card file beside the design unless
    `card` names another, and the text of the design at `path`."""
    return read_text(card_of(str(path)) if card is None else card), read_text(path)


def read_text(path: str | Path) -> str:
    """The text of a card or a design file: UTF-8 with or without a byte order mark, or
    UTF-16 with one. Windows PowerShell 5.1 writes the first with `Out-File -Encoding utf8`
    and the second with `>`. Raises OSError, or LolaSyntaxError for bytes that are neither."""
    with open(path, "rb") as fh:
        utf16 = fh.read(2) in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
    try:
        return Path(path).read_text(encoding="utf-16" if utf16 else "utf-8-sig")
    except UnicodeError as exc:
        from .lang import LolaSyntaxError

        raise LolaSyntaxError(str(path), 1, 1, f"the file is not UTF-8 or UTF-16 text ({exc})") from None
