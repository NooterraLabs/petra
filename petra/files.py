"""Reading the bytes of a card or a design file as text, and cutting what a refusal prints.
Untrusted: the trusted front end starts at the text, so a bug here costs an input error or a
check of other text, which the report shows by its path and its lines. `listed` and `summed`
word the problems of a pair that is refused already: a bug in them changes what is printed,
and not that the pair is refused. The lexer holds a text to MAX_FILE itself."""
from __future__ import annotations

import codecs
import itertools
import os
import re
from pathlib import Path
from typing import Collection, Iterable

MAX_FILE = 1_000_000
"""The most bytes a card or a design may have. A larger one is refused before it is parsed:
the front end holds a token for each few bytes and a problem for each mistake."""
MAX_PROBLEMS = 100
"""The most problems that are printed for one file, as the kernel keeps its first 100
findings. The rest are counted."""
MAX_LISTED = 4
"""The most names a message lists of a table it comes from. It says how many there are."""
MAX_MESSAGE = 500
"""The most characters of one problem that are printed. A longer one is cut, and says how
much was left out: a message may repeat a name of the file, which may be long."""
_WHERE = re.compile(r"(.+?):(\d+):(\d+): (.*)", re.DOTALL)


def listed(names: Collection[str], most: int = MAX_LISTED, like: str | None = None) -> str:
    """At most `most` of the names and how many more there are: `a, b, c, d and 44 more`.
    Without `like` they are the first ones, and it goes through no more of them than it
    lists, so a message costs the same however long the table is. With `like`, a name that
    was not found, the names that start most as it does come first, so that a name one
    letter off is among the four: this goes through the table once."""
    if like is None:
        shown = itertools.islice(names, most)
    else:
        shown = sorted(names, key=lambda name: -len(os.path.commonprefix((name, like))))[:most]
    return ", ".join(shown) + (f" and {len(names) - most:,} more" if len(names) > most else "") if names else "nothing"


def summed(problems: Iterable[str]) -> tuple[str, ...]:
    """What is printed of the problems of a card and a design. Each message is printed once,
    at the first place it arose, with how many times it arose. A message is cut to
    MAX_MESSAGE characters. For each file at most MAX_PROBLEMS are printed, and then how
    many more there were. So what a refusal prints is bounded whatever the files hold."""
    first: dict[tuple[str, str], list] = {}
    for problem in problems:
        found = _WHERE.fullmatch(problem)
        file, where, message = (found[1], f"{found[1]}:{found[2]}:{found[3]}: ", found[4]) if found else ("", "", problem)
        if (file, message) in first:
            first[file, message][1] += 1
        else:
            first[file, message] = [where, 1]
    out, kept, more = [], {}, {}
    for (file, message), (where, times) in first.items():
        if kept.get(file, 0) >= MAX_PROBLEMS:
            more[file] = more.get(file, 0) + 1
            continue
        kept[file] = kept.get(file, 0) + 1
        if len(message) > MAX_MESSAGE:
            message = f"{message[:MAX_MESSAGE]}... ({len(message) - MAX_MESSAGE:,} more characters)"
        out.append(where + message + (f" ({times:,} times, first here)" if times > 1 else ""))
    return (*out, *(f"{file + ': ' if file else ''}and {count:,} more problems" for file, count in more.items()))


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
    and the second with `>`. Raises OSError, or LolaSyntaxError for bytes that are neither
    and for a file of more than MAX_FILE bytes, which is refused before it is read."""
    from .lang.lexer import LolaSyntaxError

    size = os.path.getsize(path)
    if size > MAX_FILE:
        raise LolaSyntaxError(str(path), 1, 1, f"the file has {size:,} bytes, and a card or a design has at most {MAX_FILE:,}")
    with open(path, "rb") as fh:
        utf16 = fh.read(2) in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
    try:
        return Path(path).read_text(encoding="utf-16" if utf16 else "utf-8-sig")
    except UnicodeError as exc:
        raise LolaSyntaxError(str(path), 1, 1, f"the file is not UTF-8 or UTF-16 text ({exc})") from None
