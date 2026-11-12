"""Tokenizer for .petra. Trusted front end.

Tokens: IDENT ([A-Za-z_][A-Za-z0-9_]*), NUMBER (optional sign, integer, decimal, or p/q;
never an exponent, so every literal is exact), STRING ("..." with \\" and \\\\ escapes),
punctuation { } ( ) [ ] , : . -> -- <= >= > %, and NEWLINE. Line ends are tokens
because a component block is a list of attribute lines; runs of blank lines and comment
lines collapse into one NEWLINE, and a NEWLINE inside ( ) or [ ] is dropped. Other
whitespace separates tokens. Comments run from # to end of line. Units are IDENTs (kN,
mm2, degC, Nm) or "%". A "^" written directly after a name, with digits directly after it,
is the power of a unit, as in inch^4, and lexes as IDENT "^" NUMBER. A "^" anywhere else
is an error.

A "." written directly between two names continues a dotted name, and the segment after
it may start with a digit, so registry ids such as aluminium.6061_T6 and chs.60_3x3_2
lex as IDENT "." IDENT. The token stream always ends with NEWLINE EOF.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    IDENT = "ident"
    NUMBER = "number"
    STRING = "string"
    PUNCT = "punct"
    NEWLINE = "newline"
    EOF = "eof"


@dataclass(frozen=True, slots=True)
class Token:
    kind: Kind
    text: str
    line: int
    col: int


class LolaSyntaxError(ValueError):
    """Carries path, line, col and a message that names the expected token."""

    def __init__(self, path: str, line: int, col: int, message: str) -> None:
        super().__init__(f"{path}:{line}:{col}: {message}")
        self.path = path
        self.line = line
        self.col = col


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SEGMENT = re.compile(r"[A-Za-z0-9_]+")
_NUMBER = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+|/[0-9]+)?")
_POWER = re.compile(r"[0-9]{1,3}(?![0-9./])")
"""The power of a unit: digits right after the `^` that follows a name, with no sign, point
or `/`. Which powers a unit takes is for units.py to say."""
_PUNCT2 = ("->", "--", "<=", ">=")
LONGEST_NUMBER = 100
"""The most characters a number has. No quantity is written longer, and exact arithmetic
on a longer one costs more than a check should."""
_PUNCT1 = "{}()[],:.>%"
_OPEN, _CLOSE = "([", ")]"


def tokenize(text: str, path: str) -> tuple[Token, ...]:
    from ..files import MAX_FILE

    # A text that comes as an argument and not from a file is held to the size of a file.
    if len(text) > MAX_FILE or len(text.encode("utf-8", "surrogatepass")) > MAX_FILE:
        raise LolaSyntaxError(path, 1, 1, f"the text has over {MAX_FILE:,} bytes, and a card or a design has at most that many")
    tokens: list[Token] = []
    i, line, line_start, depth = 0, 1, 0, 0

    def emit(kind: Kind, value: str, start: int) -> None:
        tokens.append(Token(kind, value, line, start - line_start + 1))

    def fail(at: int, message: str) -> LolaSyntaxError:
        return LolaSyntaxError(path, line, at - line_start + 1, message)

    while i < len(text):
        ch = text[i]
        if ch == "\n":
            if depth == 0 and tokens and tokens[-1].kind is not Kind.NEWLINE:
                emit(Kind.NEWLINE, "\n", i)
            i += 1
            line, line_start = line + 1, i
        elif ch in " \t\r":
            i += 1
        elif ch == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
        elif ch == '"':
            start, i, chars = i, i + 1, []
            while True:
                if i >= len(text) or text[i] == "\n":
                    raise fail(start, "unterminated string")
                if text[i] == '"':
                    break
                if text[i] == "\\":
                    if i + 1 >= len(text) or text[i + 1] not in '"\\':
                        raise fail(i, 'unknown escape in string: only \\" and \\\\ are allowed')
                    i += 1
                chars.append(text[i])
                i += 1
            emit(Kind.STRING, "".join(chars), start)
            i += 1
        elif text.startswith(_PUNCT2, i):
            emit(Kind.PUNCT, text[i:i + 2], i)
            i += 2
        elif m := _NUMBER.match(text, i):
            if len(m.group()) > LONGEST_NUMBER:
                raise fail(i, f"a number has at most {LONGEST_NUMBER} characters, and this one has {len(m.group())}")
            if "/" in m.group() and int(m.group().split("/")[1]) == 0:
                raise fail(i, f"zero denominator in {m.group()}")
            emit(Kind.NUMBER, m.group(), i)
            i = m.end()
        elif m := _IDENT.match(text, i):
            emit(Kind.IDENT, m.group(), i)
            i = m.end()
            while text.startswith(".", i) and (seg := _SEGMENT.match(text, i + 1)):
                emit(Kind.PUNCT, ".", i)
                emit(Kind.IDENT, seg.group(), i + 1)
                i = seg.end()
            if text.startswith("^", i):
                power = _POWER.match(text, i + 1)
                if not power:
                    raise fail(i, "a power is written right after its unit, as in inch^4: '^' and a whole number")
                emit(Kind.PUNCT, "^", i)
                emit(Kind.NUMBER, power.group(), i + 1)
                i = power.end()
        elif ch in _PUNCT1:
            if ch in _OPEN:
                depth += 1
            elif ch in _CLOSE and depth > 0:
                depth -= 1
            emit(Kind.PUNCT, ch, i)
            i += 1
        elif ch == "-" and tokens and tokens[-1].kind is Kind.IDENT and tokens[-1].line == line \
                and line_start + tokens[-1].col - 1 + len(tokens[-1].text) == i:
            raise fail(i, f"unexpected character '-' after {tokens[-1].text}: a name is letters, digits and _, "
                          "so write _ where a designation has -")
        else:
            raise fail(i, f"unexpected character {ch!r}")
    if tokens and tokens[-1].kind is not Kind.NEWLINE:
        emit(Kind.NEWLINE, "\n", i)
    emit(Kind.EOF, "", i)
    return tuple(tokens)
