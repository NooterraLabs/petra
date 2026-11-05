"""Tokenizer for .lola. Trusted front end.

Tokens: IDENT ([A-Za-z_][A-Za-z0-9_]*), NUMBER (optional sign, integer, decimal, or p/q;
never an exponent, so every literal is exact), STRING ("..." with \\" and \\\\ escapes),
punctuation { } ( ) [ ] , : . -> -- <= >= > %, and NEWLINE. Line ends are tokens
because a component block is a list of attribute lines; runs of blank lines and comment
lines collapse into one NEWLINE, and a NEWLINE inside ( ) or [ ] is dropped. Other
whitespace separates tokens. Comments run from # to end of line. Units are IDENTs (kN,
mm2, degC, Nm) or "%".

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
_PUNCT2 = ("->", "--", "<=", ">=")
_PUNCT1 = "{}()[],:.>%"
_OPEN, _CLOSE = "([", ")]"


def tokenize(text: str, path: str) -> tuple[Token, ...]:
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
        elif ch in _PUNCT1:
            if ch in _OPEN:
                depth += 1
            elif ch in _CLOSE and depth > 0:
                depth -= 1
            emit(Kind.PUNCT, ch, i)
            i += 1
        else:
            raise fail(i, f"unexpected character {ch!r}")
    if tokens and tokens[-1].kind is not Kind.NEWLINE:
        emit(Kind.NEWLINE, "\n", i)
    emit(Kind.EOF, "", i)
    return tuple(tokens)
