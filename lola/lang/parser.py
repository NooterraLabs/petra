"""Recursive-descent parser for the grammar in syntax.py. Trusted front end.

One function per grammar rule. No backtracking beyond one token of lookahead, except the
claim rule, which looks for "P" "(" to pick the probability form. A leading IDENT that is
not in DECLS starts a component block; whether it names a registered kind is checked by
lower.py against models.KINDS, so the parser knows no component kind.

The tree it builds (lower.py reads it; leaves are lexer Tokens, so every name keeps its
position):

    design      (name, items)             items: owner (STRING) | environment (IDENT)
    param       (name, range)
    ambient     (bound | paramref)
    component   (kind, name, attrs)       attr: (key, args)
    load        (name, entries, sig?)     entry: (path, field, bound | paramref)
    tests       (name, path, trials, failures, level, sig?, block sig?)
    claim       (name, qoi, rel, qty, under)
    prob_exceeds (name, qoi, threshold, p, load)          the RangeMean form
    prob_fails  (name, path, level, p, confidence, tests) the FromTests form
    waive       (mode ref, path, owner, reason)

    bound (range,) props mean?, sig?     paramref (name,)     sig (kind, owner, source)
    range (lo, hi)    qty (number, unit?)    tuple (qty, ...)    qoi (path, name)
    ref and path (IDENT, ...)    text (STRING,)    punct (PUNCT,)
"""
from __future__ import annotations

from .lexer import Kind, LolaSyntaxError, Token, tokenize
from .syntax import File, Node

DECLS: tuple[str, ...] = ("design", "param", "ambient", "load", "tests", "claim", "waive")
"""Design-level keywords. Component kinds are not here: they belong to the domains."""

LANGUAGE_VERSION = 0

NOT_UNITS: frozenset[str] = frozenset({"in", "mean", "signed", "measured", "source", "param", "under", "from", "margin"})
"""Words the grammar puts right after a quantity, so an IDENT after a NUMBER is its unit
unless it is one of these."""

_SIGNATURE = ("signed", "measured")
_AFTER_RANGE = ("mean", "signed", "measured", "source")
_ATTR_PUNCT = (":", "--", "->")


def _describe(tok: Token) -> str:
    if tok.kind is Kind.NEWLINE:
        return "end of line"
    if tok.kind is Kind.EOF:
        return "end of file"
    if tok.kind is Kind.STRING:
        return f"string {tok.text!r}"
    if tok.kind is Kind.NUMBER:
        return f"number {tok.text}"
    return f"'{tok.text}'"


def _node(head: str, at: Token, *args: object, **props: object) -> Node:
    return Node(head, args, props, at.line, at.col)


class Parser:
    def __init__(self, tokens: tuple[Token, ...], path: str) -> None:
        self.tokens = tokens
        self.path = path
        self.pos = 0

    # --- token access ------------------------------------------------------------

    def _peek(self, ahead: int = 0) -> Token:
        return self.tokens[min(self.pos + ahead, len(self.tokens) - 1)]

    def _is(self, kind: Kind, text: str | None = None, ahead: int = 0) -> bool:
        tok = self._peek(ahead)
        return tok.kind is kind and (text is None or tok.text == text)

    def _next(self) -> Token:
        tok = self._peek()
        self.pos = min(self.pos + 1, len(self.tokens) - 1)
        return tok

    def _error(self, tok: Token, message: str) -> LolaSyntaxError:
        return LolaSyntaxError(self.path, tok.line, tok.col, message)

    def _expect(self, kind: Kind, text: str | None, what: str) -> Token:
        if self._is(kind, text):
            return self._next()
        raise self._error(self._peek(), f"expected {what}, found {_describe(self._peek())}")

    def _word(self, word: str) -> Token:
        return self._expect(Kind.IDENT, word, f"'{word}'")

    def _punct(self, text: str) -> Token:
        return self._expect(Kind.PUNCT, text, f"'{text}'")

    def _ident(self, what: str) -> Token:
        return self._expect(Kind.IDENT, None, what)

    def _string(self, what: str) -> Token:
        return self._expect(Kind.STRING, None, what)

    def _newline(self) -> None:
        self._expect(Kind.NEWLINE, None, "end of line")

    def _int(self, what: str) -> tuple[Token, int]:
        tok = self._expect(Kind.NUMBER, None, what)
        if not tok.text.isascii() or not tok.text.isdigit():
            raise self._error(tok, f"expected {what} as a whole number, found {tok.text}")
        return tok, int(tok.text)

    def _open_block(self) -> None:
        self._punct("{")
        self._newline()

    # --- file and declarations --------------------------------------------------

    def file(self) -> File:
        self._expect(Kind.IDENT, "lola", f"the header 'lola {LANGUAGE_VERSION}'")
        tok, version = self._int("the language version")
        if version != LANGUAGE_VERSION:
            raise self._error(tok, f"unsupported language version {version}; this front end reads lola {LANGUAGE_VERSION}")
        self._newline()
        decls = []
        while not self._is(Kind.EOF):
            decls.append(self.decl())
            self._newline()
        return File(self.path, version, tuple(decls))

    def decl(self) -> Node:
        """Dispatch on the leading keyword through DECLS; any other IDENT followed by an
        IDENT and "{" is a component block. Anything else raises LolaSyntaxError listing
        the keywords DECLS accepts."""
        tok = self._peek()
        if tok.kind is Kind.IDENT and tok.text in DECLS:
            return getattr(self, f"_{tok.text}")()
        if tok.kind is Kind.IDENT and self._is(Kind.IDENT, ahead=1) and self._is(Kind.PUNCT, "{", ahead=2):
            return self._component()
        raise self._error(tok, f"expected a declaration ({', '.join(DECLS)}) or a component block '<kind> <name> {{', found {_describe(tok)}")

    def _design(self) -> Node:
        kw = self._word("design")
        name = self._string("the design name")
        self._open_block()
        items = []
        while not self._is(Kind.PUNCT, "}"):
            tok = self._peek()
            if self._is(Kind.IDENT, "owner"):
                self._next()
                items.append(_node("owner", tok, self._string("the owner")))
            elif self._is(Kind.IDENT, "environment"):
                self._next()
                items.append(_node("environment", tok, self._ident("an environment id")))
            else:
                raise self._error(tok, f"expected 'owner', 'environment' or '}}', found {_describe(tok)}")
            self._newline()
        self._next()
        return _node("design", kw, name, tuple(items))

    def _param(self) -> Node:
        kw = self._word("param")
        name = self._ident("a param name")
        self._word("in")
        return _node("param", kw, name, self._range())

    def _ambient(self) -> Node:
        kw = self._word("ambient")
        return _node("ambient", kw, self._bound())

    def _component(self) -> Node:
        kind = self._ident("a component kind")
        name = self._ident("a component name")
        self._open_block()
        attrs = []
        while not self._is(Kind.PUNCT, "}"):
            key = self._ident("an attribute name or '}'")
            args = []
            while not self._is(Kind.NEWLINE) and not self._is(Kind.EOF):
                args.append(self._arg())
            self._newline()
            attrs.append(_node("attr", key, key, tuple(args)))
        self._next()
        return _node("component", kind, kind, name, tuple(attrs))

    def _load(self) -> Node:
        kw = self._word("load")
        name = self._ident("a load case name")
        self._open_block()
        entries = []
        while self._is(Kind.IDENT, "on"):
            on = self._next()
            target = self._path("a load target")
            field = self._ident("a load field")
            entries.append(_node("entry", on, target, field, self._bound()))
            self._newline()
        sig = None
        if self._at_signature():
            sig = self._signature()
            self._newline()
        self._expect(Kind.PUNCT, "}", "'on', a signature or '}'")
        return _node("load", kw, name, tuple(entries), sig)

    def _tests(self) -> Node:
        kw = self._word("tests")
        name = self._ident("a tests name")
        self._open_block()
        self._word("on")
        subject = self._path("the tested component")
        self._word("trials")
        _, trials = self._int("the number of trials")
        self._word("failures")
        _, failures = self._int("the number of failures")
        self._word("at")
        level = self._qty()
        sig = self._signature() if self._at_signature() else None
        self._newline()
        block_sig = None
        if self._at_signature():
            block_sig = self._signature()
            self._newline()
        self._expect(Kind.PUNCT, "}", "a signature or '}'")
        return _node("tests", kw, name, subject, trials, failures, level, sig, block_sig)

    def _claim(self) -> Node:
        kw = self._word("claim")
        name = self._ident("a claim name")
        self._punct(":")
        if self._is(Kind.IDENT, "P") and self._is(Kind.PUNCT, "(", ahead=1):
            self._next()
            self._next()
            if self._is(Kind.IDENT, "fail") and self._is(Kind.IDENT, ahead=1):
                self._next()
                subject = self._path("the component that fails")
                self._word("at")
                level = self._qty()
                self._punct(")")
                self._punct("<=")
                p = self._expect(Kind.NUMBER, None, "a probability")
                self._word("confidence")
                confidence = self._qty()
                self._word("from")
                tests = self._ident("a tests name")
                return _node("prob_fails", kw, name, subject, level, p, confidence, tests)
            qoi = self._qoi()
            self._punct(">")
            threshold = self._qty()
            self._punct(")")
            self._punct("<=")
            p = self._expect(Kind.NUMBER, None, "a probability")
            self._word("under")
            load = self._ident("a load case name")
            return _node("prob_exceeds", kw, name, qoi, threshold, p, load)
        qoi = self._qoi()
        if not (self._is(Kind.PUNCT, "<=") or self._is(Kind.PUNCT, ">=")):
            raise self._error(self._peek(), f"expected '<=' or '>=', found {_describe(self._peek())}")
        rel = self._next()
        bound = self._qty()
        margin = None
        if self._is(Kind.IDENT, "margin"):
            self._next()
            margin = self._qty()
        under = []
        if self._is(Kind.IDENT, "under"):
            self._next()
            under.append(self._ident("a load case name"))
            while self._is(Kind.PUNCT, ","):
                self._next()
                under.append(self._ident("a load case name"))
        return _node("claim", kw, name, qoi, rel, bound, margin, tuple(under))

    def _waive(self) -> Node:
        kw = self._word("waive")
        mode = self._ref()
        self._word("on")
        subject = self._path("the waived subject")
        self._word("by")
        owner = self._string("the waiver's owner")
        self._word("reason")
        reason = self._string("the reason")
        return _node("waive", kw, mode, subject, owner, reason)

    # --- shared rules ------------------------------------------------------------

    def _arg(self) -> Node:
        tok = self._peek()
        if tok.kind is Kind.IDENT and tok.text in ("in", "param"):
            return self._bound()
        if tok.kind is Kind.IDENT and tok.text in _AFTER_RANGE:
            raise self._error(tok, f"'{tok.text}' must follow a range 'in [lo, hi]'")
        if tok.kind is Kind.IDENT:
            return self._ref()
        if tok.kind is Kind.NUMBER:
            return self._qty()
        if tok.kind is Kind.STRING:
            return _node("text", self._next(), tok)
        if self._is(Kind.PUNCT, "("):
            return self._tuple()
        if tok.kind is Kind.PUNCT and tok.text in _ATTR_PUNCT:
            return _node("punct", self._next(), tok)
        raise self._error(tok, f"unexpected {_describe(tok)} in an attribute line")

    def _bound(self) -> Node:
        tok = self._peek()
        if self._is(Kind.IDENT, "param"):
            self._next()
            return _node("paramref", tok, self._ident("a param name"))
        if not self._is(Kind.IDENT, "in"):
            raise self._error(tok, f"expected a bound 'in [lo, hi]' or 'param NAME', found {_describe(tok)}")
        self._next()
        rng = self._range()
        mean = None
        if self._is(Kind.IDENT, "mean"):
            self._next()
            mean = self._qty()
        sig = self._signature() if self._at_signature() else None
        return _node("bound", tok, rng, mean=mean, sig=sig)

    def _at_signature(self) -> bool:
        return any(self._is(Kind.IDENT, word) for word in _SIGNATURE)

    def _signature(self) -> Node:
        kind = self._peek()
        if not self._at_signature():
            raise self._error(kind, f"expected 'signed' or 'measured', found {_describe(kind)}")
        self._next()
        owner = self._string("the signer")
        self._word("source")
        source = self._string("the source")
        return _node("sig", kind, kind, owner, source)

    def _range(self) -> Node:
        open_ = self._punct("[")
        lo = self._qty()
        self._punct(",")
        hi = self._qty()
        self._punct("]")
        return _node("range", open_, lo, hi)

    def _qty(self) -> Node:
        number = self._expect(Kind.NUMBER, None, "a number")
        unit = None
        if self._is(Kind.PUNCT, "%") or (self._is(Kind.IDENT) and self._peek().text not in NOT_UNITS):
            unit = self._next()
        return _node("qty", number, number, unit)

    def _tuple(self) -> Node:
        open_ = self._punct("(")
        items = [self._qty()]
        while self._is(Kind.PUNCT, ","):
            self._next()
            items.append(self._qty())
        self._punct(")")
        return _node("tuple", open_, *items)

    def _dotted(self, head: str, what: str) -> Node:
        parts = [self._ident(what)]
        while self._is(Kind.PUNCT, "."):
            self._next()
            parts.append(self._ident("a name after '.'"))
        return _node(head, parts[0], *parts)

    def _ref(self) -> Node:
        return self._dotted("ref", "a name")

    def _path(self, what: str) -> Node:
        return self._dotted("path", what)

    def _qoi(self) -> Node:
        first = self._peek()
        parts: list[tuple[Token, bool]] = []
        while True:
            segment = self._ident("a quantity path")
            if self._is(Kind.PUNCT, "("):
                self._next()
                parts.append((self._ident("an element name"), True))
                self._punct(")")
            else:
                parts.append((segment, False))
            if not self._is(Kind.PUNCT, "."):
                break
            self._next()
        name, selected = parts[-1]
        if selected:
            raise self._error(name, "a quantity path ends with a quantity name, as in frame.member(m1).stress")
        return _node("qoi", first, tuple(tok for tok, _ in parts[:-1]), name)


def parse(text: str, path: str) -> File:
    return Parser(tokenize(text, path), path).file()
