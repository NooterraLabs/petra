"""Evidence transport: turn a family's evidence into evidence for a query statement whose
box sits inside the family box. Untrusted. Each rule's transport relies on a kernel
theorem, so the kernel accepts the result for the query statement on its own terms:

  R4  restrict the partition to the query box: drop subtrees disjoint from it, keep
      splits that cut it. Leaves shrink, and interval arithmetic is inclusion-isotone,
      so every kept leaf still encloses <= 0. Cost: only the leaves meeting the query.
  R5  same restriction on the domination partition; multipliers unchanged.
  R1  each query vertex is a convex combination of family vertices with exact weights
      (product of per-symbol barycentric weights); x_query = sum theta x_family exactly.
  R3  same convex combination on s; u likewise (any u is admissible). Bounds may loosen
      slightly, never break, because per-vertex enclosures hold over the family box.
  R2  reuse (reference_weights, L, d) unchanged: the query's weight enclosures are
      inside the family's, so r_j <= enclose(w_j, query).lo still holds.
  R6  unchanged.
DefinedRange entries transport the same way as R3 evidence.

Every function here works in the family's symbol names. `transport` renames the result
into the query's names last, so the kernel reads it against the query statement.
"""
from __future__ import annotations

import dataclasses
from fractions import Fraction
from typing import Callable, Mapping

from ..kernel import DefinedHyp, Evidence, Expr, Interval, Leaf, Partition, RangeHyp, Split, Statement, enclose, free_syms
from ..kernel.rules.r1_linear import FeasiblePoints
from ..kernel.rules.r2_definite import LDLFactor
from ..kernel.rules.r3_hypercircle import Hypercircle, HypercircleFields
from ..kernel.rules.r4_enclosure import Enclosure
from ..kernel.rules.r5_moment import MomentDual
from ..kernel.rules.r6_scenario import Arithmetic

Box = dict[str, Interval]


@dataclasses.dataclass(frozen=True)
class _Frame:
    """The two boxes in family symbol names, and the renaming into query names. Each
    DefinedHyp symbol spans its proven range in both boxes, as the kernel's box does."""

    family: Box
    query: Box
    renaming: Mapping[str, str]


def transport(family_statement: Statement, family_evidence: Evidence, query: Statement, renaming: dict[str, str]) -> Evidence:
    """`renaming` maps every family symbol, bound random variables included, to the query
    symbol with the same canonical name. Raises ValueError for evidence with no
    transport: refutations, which the library never stores."""
    frame = _frame(family_statement, family_evidence, query, renaming)
    definitions = {h.sym: h.definition for h in family_statement.hyps if isinstance(h, DefinedHyp)}
    pieces = ((family_evidence.body, _BODIES), *((r.proof, _LEMMAS) for r in family_evidence.defined))
    for proof, table in pieces:
        if type(proof) not in table:
            raise ValueError(f"{type(proof).__name__} evidence has no transport")
    defined = tuple(dataclasses.replace(r, proof=_LEMMAS[type(r.proof)](definitions[r.sym], r.proof, frame)) for r in family_evidence.defined)
    body = _BODIES[type(family_evidence.body)](family_statement.goal, family_evidence.body, frame)
    return _renamed(Evidence(body, defined), renaming)


def _frame(family: Statement, evidence: Evidence, query: Statement, renaming: Mapping[str, str]) -> _Frame:
    ranges = {r.sym: Interval(r.lo, r.hi) for r in evidence.defined}
    own = {h.sym: Interval(h.lo, h.hi) for h in family.hyps if isinstance(h, RangeHyp)}
    theirs = {h.sym: Interval(h.lo, h.hi) for h in query.hyps if isinstance(h, RangeHyp)}
    return _Frame({**own, **ranges}, {**{f: theirs[renaming[f]] for f in own}, **ranges}, renaming)


def restrict_partition(partition: Partition, query_box: dict) -> Partition:
    """Split(sym, at) with at <= query.lo(sym) -> restrict(right); at >= query.hi(sym) ->
    restrict(left); else keep the split with both children restricted to their halves of
    the query box. Every kept split point lies strictly inside its query cell, as the
    kernel requires, and every leaf's query cell lies inside its family leaf."""
    while isinstance(partition, Split):
        cell = query_box[partition.sym]
        if partition.at <= cell.lo:
            partition = partition.right
        elif partition.at >= cell.hi:
            partition = partition.left
        else:
            at = partition.at
            left = restrict_partition(partition.left, {**query_box, partition.sym: Interval(cell.lo, at)})
            right = restrict_partition(partition.right, {**query_box, partition.sym: Interval(at, cell.hi)})
            return Split(partition.sym, at, left, right)
    return partition


def barycentric(query_vertex: dict, family_box: dict, syms: tuple[str, ...]) -> tuple:
    """Exact weights over the 2**k family vertices, in kernel vertex order (bit k of the
    index selects hi of syms[k]). The weights are non-negative, sum to 1, and their
    combination of the family vertices is query_vertex. A point range puts its weight on
    its lo vertex."""
    weights = [Fraction(1)]
    for sym in syms:
        iv = family_box[sym]
        t = (query_vertex[sym] - iv.lo) / (iv.hi - iv.lo) if iv.hi > iv.lo else Fraction(0)
        weights = [w * (1 - t) for w in weights] + [w * t for w in weights]
    return tuple(weights)


def _vertices(box: Mapping[str, Interval], syms: tuple[str, ...]) -> list[dict]:
    return [{s: box[s].hi if v >> k & 1 else box[s].lo for k, s in enumerate(syms)} for v in range(1 << len(syms))]


def _combine(vectors: tuple, exprs: tuple[Expr, ...], frame: _Frame) -> tuple:
    """Per-vertex vectors for the query, in the query's vertex order. The kernel orders
    vertices by sorted symbol name, and the query's names sort differently from the
    family's, so each query vertex is built in query order and weighed in family order."""
    family_syms = tuple(sorted(free_syms(exprs)))
    by_query_name = sorted(family_syms, key=lambda s: frame.renaming[s])
    out = []
    for vertex in _vertices(frame.query, tuple(by_query_name)):
        weights = barycentric(vertex, frame.family, family_syms)
        out.append(tuple(sum((w * x[i] for w, x in zip(weights, vectors) if w), Fraction(0)) for i in range(len(vectors[0]))))
    return tuple(out)


def _fields(fields: HypercircleFields, rhs: tuple[Expr, ...], frame: _Frame) -> HypercircleFields:
    return HypercircleFields(_combine(fields.s, rhs, frame), _combine(fields.u, rhs, frame))


def _moment(goal, body: MomentDual, frame: _Frame) -> MomentDual:
    support = {x.sym: Interval(enclose(x.lo, frame.query).lo, enclose(x.hi, frame.query).hi) for x in goal.random}
    return MomentDual(body.y0, body.y, restrict_partition(body.partition, {**frame.query, **support}))


_BODIES: Mapping[type, Callable] = {
    Enclosure: lambda goal, body, frame: Enclosure(restrict_partition(body.partition, frame.query)),
    MomentDual: _moment,
    FeasiblePoints: lambda goal, body, frame: FeasiblePoints(_combine(body.x, goal.b, frame)),
    Hypercircle: lambda goal, body, frame: Hypercircle(_fields(body.fields, goal.problem.f, frame)),
    LDLFactor: lambda goal, body, frame: body,
    Arithmetic: lambda goal, body, frame: body,
}
"""Proof body type -> its transport. A rule with no entry has no reuse."""

_LEMMAS: Mapping[type, Callable] = {
    HypercircleFields: lambda definition, proof, frame: _fields(proof, definition.problem.f, frame),
}
"""Lemma evidence type -> its transport, given the DefinedHyp's definition."""


def _renamed(term, renaming: Mapping[str, str]):
    """The evidence with every symbol a solver named (split symbols, DefinedRange
    symbols) moved into the query's names."""
    if isinstance(term, tuple):
        return tuple(_renamed(t, renaming) for t in term)
    if isinstance(term, Leaf) or not dataclasses.is_dataclass(term) or isinstance(term, type):
        return term
    changes = {}
    for f in dataclasses.fields(term):
        value = getattr(term, f.name)
        new = renaming[value] if f.name == "sym" and isinstance(value, str) else _renamed(value, renaming)
        if new is not value:
            changes[f.name] = new
    return dataclasses.replace(term, **changes) if changes else term
