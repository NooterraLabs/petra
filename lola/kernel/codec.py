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

The decoder is the kernel's only input boundary, so it is trusted and validated here.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from . import rules
from .evidence import DefinedRange, Evidence, Leaf, Split
from .terms import (
    Abs,
    Add,
    Const,
    DefinedHyp,
    Div,
    Exp,
    Ln,
    Matrix,
    Max,
    Min,
    Mul,
    Neg,
    Pi,
    PowInt,
    RangeHyp,
    Sqrt,
    Statement,
    Sym,
)

FORMAT = "lola-kernel/0"
"""Version of the term encoding. Bumped on any change to TAGS or field spellings."""

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


class DecodeError(ValueError):
    """Malformed or non-canonical JSON. The message names the JSON path."""


def encode_statement(statement: Statement) -> dict[str, Any]:
    raise NotImplementedError


def decode_statement(obj: Any) -> Statement:
    raise NotImplementedError


def encode_evidence(evidence: Evidence) -> dict[str, Any]:
    raise NotImplementedError


def decode_evidence(obj: Any) -> Evidence:
    raise NotImplementedError


def canonical_text(obj: Any) -> str:
    raise NotImplementedError


def statement_hash(statement: Statement) -> str:
    """sha256 of the canonical encoding. The pipeline binds a stored certificate to an
    obligation by this hash, so it must be identical across runs and platforms."""
    raise NotImplementedError


def evidence_hash(evidence: Evidence) -> str:
    raise NotImplementedError


def _encode(term: Any) -> Any:
    """Generic encoder: dataclass -> {"t": tag, field: encode(value)}, Fraction -> string,
    tuple -> list, None -> null. Field order comes from dataclasses.fields()."""
    raise NotImplementedError


def _decode(obj: Any, expected: Any, path: str) -> Any:
    """Generic strict decoder driven by the dataclass field annotations of the tagged
    class. `expected` is the annotated type at this position, used to reject a goal where
    an expr is required."""
    raise NotImplementedError
