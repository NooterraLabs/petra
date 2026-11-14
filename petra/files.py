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
import sys
from pathlib import Path
from typing import Any, Callable, Collection, Iterable

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
_ACTED_ON = re.compile("[\\x00-\\x09\\x0b-\\x1f\\x7f-\\x9f\\u061c\\u200e\\u200f\\u2028\\u2029\\u202a-\\u202e\\u2066-\\u2069]")
"""Every character of `escaped`, and the carriage return."""


def escaped(c: str) -> bool:
    """Whether the kernel prints this character as an escape of six bytes, `\\uXXXX`
    (`escaped` in kernel/Petra/Files.lean). A terminal acts on these and does not show them:
    the control characters, which are those under U+0020 but the line feed and the carriage
    return, and U+007F to U+009F; the line and the paragraph separator; and the marks that
    turn the direction of text."""
    n = ord(c)
    return (n < 0x20 and c not in "\n\r") or 0x7F <= n <= 0x9F or n in (0x2028, 0x2029, 0x61C, 0x200E, 0x200F) or 0x202A <= n <= 0x202E or 0x2066 <= n <= 0x2069


def shown(text: str) -> str:
    """A text for a terminal: its lines as they are, and every other character that a
    terminal acts on written as the kernel prints it, `\\u` and four digits. A carriage
    return is one of them here: it sends the cursor back to the start of its line."""
    return _ACTED_ON.sub(lambda found: f"\\u{ord(found[0]):04x}", text)


class Shown:
    """A stream that writes every text as `shown` gives it, so that nothing a card, a design
    or a deck holds reaches a terminal as a character it acts on: the lines of a report are
    its own, and an escape, a backspace or a carriage return in a name or a reason is printed
    as `\\u001b`, `\\u0008` or `\\u000d`. Everything else is the stream's own."""

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def write(self, text: str) -> int:
        self._stream.write(shown(text))
        return len(text)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def guarded(run: Callable[[list[str]], int], argv: list[str], who: str = "petra") -> int:
    """Run a command with its two streams printing as `shown`, and refuse an argument that
    holds a character a terminal acts on or a line end, with exit code 3. A report and a
    refusal print the names of files, and a report keeps its own line feeds: a folder named
    with one would write whole lines of a report that no command made."""
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = Shown(out), Shown(err)
    try:
        for arg in argv:
            if _ACTED_ON.search(arg) or "\n" in arg:
                print(f"{who}: an argument holds a character that a terminal acts on, or a line end: {shown(arg).replace(chr(10), chr(92) + 'u000a')}", file=sys.stderr)
                return 3
        return run(argv)
    finally:
        sys.stdout, sys.stderr = out, err


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
