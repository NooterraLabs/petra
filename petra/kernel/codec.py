"""Language-neutral JSON for statements and evidence, plus canonical hashing.

The JSON spelling is the portability contract with a future Lean kernel. Rules:
- Every term is a JSON object with a "t" tag naming its variant ("add", "sym",
  "linear_feasible", "ldl", ...). TAGS below joins the core tags listed here with the
  tags each rule declares in its RuleSpec, and refuses a tag or a class tagged twice.
- Rationals are strings in the canonical form of interval.parse_q.
- Integers that are counts or indices (rows, index, n, k, exponent) are JSON integers.
- Canonical text is `json.dumps(obj, sort_keys=True, separators=(",", ":"),
  ensure_ascii=True)`. A hash is "sha256:" + hex digest of the canonical text.
- Decoding is strict: unknown tags, unknown keys, missing keys, non-canonical rationals
  and non-canonical matrices are errors. A file has one meaning or none.
- Strings hold no surrogate code points, in either direction, so canonical text is one
  to one and two terms never share a hash except by a sha256 collision.

The decoder is the kernel's only input boundary, so it is trusted and validated here.
The encoder writes each Python value by its own type (Fraction as a string, int as an
integer), so decode(encode(term)) == term exactly when the term is well typed and
canonical. check.py uses that round trip to validate terms built in Python.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from fractions import Fraction
from types import MappingProxyType
from typing import Any, Mapping, Union, get_args, get_origin, get_type_hints

from . import rules
from .evidence import DefinedRange, Evidence, Instance, Leaf, Split
from .interval import format_q, parse_q
from .terms import (
    Abs, Add, Const, DefinedHyp, Div, Exp, Ln, Matrix, Max, Min, Mul, Neg, Pi, PowInt, RangeHyp, Sqrt, Statement, Sym,
)

FORMAT = "petra-kernel/0"
"""Version of the term encoding. Bumped when a change to TAGS or field spellings would
give an existing file another meaning or none. Adding a tag does neither: every file
that decoded before decodes to the same term."""

_CORE_TAGS: tuple[tuple[str, type], ...] = (
    ("const", Const),
    ("sym", Sym),
    ("pi", Pi),
    ("add", Add),
    ("mul", Mul),
    ("neg", Neg),
    ("div", Div),
    ("pow_int", PowInt),
    ("sqrt", Sqrt),
    ("ln", Ln),
    ("exp", Exp),
    ("abs", Abs),
    ("min", Min),
    ("max", Max),
    ("matrix", Matrix),
    ("range_hyp", RangeHyp),
    ("defined_hyp", DefinedHyp),
    ("statement", Statement),
    ("leaf", Leaf),
    ("split", Split),
    ("defined_range", DefinedRange),
    ("instance", Instance),
    ("evidence", Evidence),
)
"""Tags of the core term language in terms.py and evidence.py. Rule-specific terms are
tagged by their own RuleSpec."""


def _tags() -> Mapping[str, type]:
    out: dict[str, type] = {}
    for tag, cls in _CORE_TAGS + tuple(rules.TAGS.items()):
        if tag in out or cls in out.values():
            raise RuntimeError(f"JSON tag {tag!r} or class {cls.__name__} is tagged twice")
        out[tag] = cls
    return MappingProxyType(out)


TAGS: Mapping[str, type] = _tags()
"""JSON tag -> class: the core tags plus every tag a registered rule declares. Field keys
are the dataclass field names. Matrix entries encode as [[i, j, "p/q"], ...] in (i, j)
order. Annotations are strings (PEP 563): the decoder resolves them with
typing.get_type_hints against the defining module plus the aliases in kernel/rules
(Goal, ProofEvidence, RefutationEvidence, QuantityDef, LemmaEvidence)."""

_TAG_OF = {cls: tag for tag, cls in TAGS.items()}
_ALIASES = {name: getattr(rules, name) for name in ("Goal", "ProofEvidence", "RefutationEvidence", "QuantityDef", "LemmaEvidence")}
_FIELDS = {cls: (tuple(f.name for f in fields(cls)), get_type_hints(cls, localns=_ALIASES)) for cls in TAGS.values()}


class DecodeError(ValueError):
    """Malformed or non-canonical JSON. The message names the JSON path."""


def encode_statement(statement: Statement) -> dict[str, Any]:
    if type(statement) is not Statement:
        raise TypeError(f"expected a Statement, got {type(statement).__name__}")
    return _encode(statement)


def decode_statement(obj: Any) -> Statement:
    return _decode(obj, Statement, "$")


def encode_evidence(evidence: Evidence) -> dict[str, Any]:
    if type(evidence) is not Evidence:
        raise TypeError(f"expected Evidence, got {type(evidence).__name__}")
    return _encode(evidence)


def decode_evidence(obj: Any) -> Evidence:
    return _decode(obj, Evidence, "$")


def decode_as(obj: Any, expected: Any) -> Any:
    """Strictly decode `obj` as the annotated type `expected`, such as one field's type."""
    return _decode(obj, expected, "$")


def canonical_text(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_of(obj: Any) -> str:
    """The hash of an encoded term: "sha256:" + hex digest of its canonical text."""
    return "sha256:" + hashlib.sha256(canonical_text(obj).encode("ascii")).hexdigest()


def statement_hash(statement: Statement) -> str:
    """sha256 of the canonical encoding. The pipeline binds a stored certificate to an
    obligation by this hash, so it must be identical across runs and platforms."""
    return hash_of(encode_statement(statement))


def evidence_hash(evidence: Evidence) -> str:
    return hash_of(encode_evidence(evidence))


def _encode(term: Any) -> Any:
    """Generic encoder: dataclass -> {"t": tag, field: encode(value)}, Fraction -> string,
    tuple -> list, None -> null. Field order comes from dataclasses.fields(). Raises
    TypeError for anything that is not a kernel value, such as a float or a bool. Terms
    are tested first because most nodes are terms, and a test against Fraction is slow."""
    kind = type(term)
    if kind in _TAG_OF:
        return {"t": _TAG_OF[kind], **{name: _encode(getattr(term, name)) for name in _FIELDS[kind][0]}}
    if kind is tuple:
        return [_encode(x) for x in term]
    if isinstance(term, Fraction):
        return format_q(term)
    if term is None or kind is int:
        return term
    if kind is str:
        return _text(term, TypeError, "$")
    raise TypeError(f"{kind.__name__} is not a kernel term")


def _text(s: str, error: type, path: str) -> str:
    """`s`, if no other string has its canonical text. ensure_ascii spells a surrogate
    pair and the character it encodes the same way, so a string holding a surrogate code
    point could share its canonical text, and its hash, with another string."""
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        raise error(f"{path}: a string may not hold a surrogate code point") from None
    return s


def _decode(obj: Any, expected: Any, path: str) -> Any:
    """Generic strict decoder driven by the dataclass field annotations of the tagged
    class. `expected` is the annotated type at this position, used to reject a goal where
    an expr is required."""
    if expected is Fraction:
        try:
            return parse_q(obj)
        except ValueError:
            raise DecodeError(f"{path}: expected a canonical rational string, got {obj!r:.80}") from None
    if expected in (int, str):
        if type(obj) is not expected:
            raise DecodeError(f"{path}: expected {expected.__name__}, got {obj!r:.80}")
        return _text(obj, DecodeError, path) if expected is str else obj
    if get_origin(expected) is tuple:
        kinds = get_args(expected)
        if type(obj) is not list or (kinds[-1] is not Ellipsis and len(obj) != len(kinds)):
            raise DecodeError(f"{path}: expected a list matching {expected}, got {obj!r:.80}")
        kinds = (kinds[0],) * len(obj) if kinds[-1] is Ellipsis else kinds
        return tuple(_decode(x, kind, f"{path}[{i}]") for i, (x, kind) in enumerate(zip(obj, kinds)))
    allowed = get_args(expected) if get_origin(expected) is Union else (expected,)
    if obj is None and type(None) in allowed:
        return None
    cls = TAGS.get(obj["t"]) if type(obj) is dict and type(obj.get("t")) is str else None
    if cls not in allowed:
        tags = sorted(_TAG_OF.get(a, "null") for a in allowed)
        raise DecodeError(f"{path}: expected a term tagged {tags}, got {obj!r:.80}")
    names, hints = _FIELDS[cls]
    if set(obj) != {"t", *names}:
        raise DecodeError(f"{path}: {obj['t']} takes exactly the keys {sorted(names)}, got {sorted(set(obj) - {'t'})}")
    term = cls(**{name: _decode(obj[name], hints[name], f"{path}.{name}") for name in names})
    if cls is Matrix:
        _check_matrix(term, path)
    return term


def _check_matrix(m: Matrix, path: str) -> None:
    if m.rows < 0 or m.cols < 0:
        raise DecodeError(f"{path}: a matrix needs non-negative dimensions")
    previous = (-1, -1)
    for i, j, v in m.entries:
        if not (0 <= i < m.rows and 0 <= j < m.cols) or v == 0 or (i, j) <= previous:
            raise DecodeError(f"{path}: matrix entries must be in range, nonzero and strictly increasing in (i, j)")
        previous = (i, j)
