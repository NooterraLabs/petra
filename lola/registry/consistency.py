"""Physics-consistency checker for decks. Untrusted: a finding can only add an open item
needing RegistryInconsistent (models.base) for entries a design uses, never remove one,
so a bug here cannot produce a false PASS. `lola registry check` runs check_deck on a
deck; tests/test_registry_consistency.py runs it on the shipped deck and on corrupted
copies.

Each Relation is a physical law or a standard's defining formula, written as two kernel
Exprs over the record values of one entry (and the constants). Sym("<entry>.<prop>")
names a record of the entry and Sym("const.<name>") a constant record. The checker
encloses both sides rigorously and flags the entry only when the enclosures are farther
apart than the relation's tolerance, so a finding is itself a certified disagreement.

A relation applies to an entry with its prefix whose deck holds the record on the left.
A missing record on the right, or a side that cannot be evaluated, is a finding: the
record on the left cannot be checked. Every record's provenance is checked too, as the
relation "record.provenance". A derived record whose formula is a single premise key
(a cable's alpha is const.cu.alpha20) is a copy and must equal that record exactly, as
the relation "record.copy". Every other derived record is the left side of a relation, so
every derived number in a deck is re-derived.

v0 relations (each catches a class of corrupted record):
  bolt.stress_area       As      == (pi/4)((d2 + d3)/2)^2              tol 0.5 %
  thread.stress_area_table   ISO 898-1 As,nom, the same relation       tol 0.5 %
  bolt.proof_load        Fp      == Sp * As                            tol 0.5 %
  bolt.class_ratio       second digit of class / 10 == Rp02/Rm         tol 2 %
  bolt.yield_order       Rp02_min <= Rm_min
  thread.*_coefficient   ISO 724 coefficients == 3 sqrt 3 / 8, 17 sqrt 3 / 24   tol 1e-6
  cable.resistance       R20     in [rho20/A, 1.10 * rho20/A]           (IEC 60228 allowance)
  conductor.resistance_table   IEC 60228 maximum, the same band
  cable.k_factor         k       == sqrt(qc (beta+20)/rho20 ln((beta+tf)/(beta+ti)))  tol 1 %
  insulation.k_factor_table    k = 115 of IEC 60364-4-43, the same relation         tol 1 %
  copper.adiabatic_constant    K = 226 == sqrt(qc (beta + 20) / rho20)   tol 0.5 %
  copper.temperature_coefficient   alpha20 == 1 / (beta + 20)           tol 0.5 %
  cable.conductor_diameter, cable.outer_diameter, cable.insulation_thermal_resistance
  material.shear_modulus G       == E / (2 (1 + nu))                   tol 2 %
  material.yield_order   fy      <= fu
  section.area           A       == (pi/4)(D^2 - (D - 2t)^2)           tol 0.5 %
  section.second_moment  I       == (pi/64)(D^4 - (D - 2t)^4)          tol 0.5 %
  breaker.conventional_* I_t     == 1.45 In, I_nt == 1.13 In           exact
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Callable, Mapping

from ..kernel import Add, Const, Div, Expr, Interval, Ln, Mul, Neg, Pi, PowInt, Sqrt, Sym
from .deck import Deck, DeckRecord, provenance_problem
from .enclosure import EvaluationError, decimal, enclose, free_syms, interval_text, render

_PREMISE_KEY = re.compile(r"[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+")

@dataclass(frozen=True)
class Relation:
    id: str
    applies_to: str                         # entry prefix: "bolt.", "cable.", "const.cu", "" for any
    lhs: Callable[[Deck, str], Expr]        # build the Expr for one entry id
    rhs: Callable[[Deck, str], Expr]
    rel_tol: Fraction
    kind: str = "eq"                        # "eq", "le", or "within"


@dataclass(frozen=True)
class Finding:
    """lhs and rhs are the enclosures compared. When the right side could not be
    evaluated, rhs repeats lhs; when the left side could not, both are 0. The message
    says why."""

    entry: str
    relation: str
    lhs: Interval
    rhs: Interval
    message: str


def _rec(prop: str) -> Callable[[Deck, str], Expr]:
    return lambda deck, entry: Sym(f"{entry}.{prop}")


def _c(name: str) -> Sym:
    return Sym(f"const.{name}")


def _n(value: int | str | Fraction) -> Const:
    return Const(Fraction(value))


def _stress_area(deck: Deck, e: str) -> Expr:
    d, p = Sym(f"{e}.d"), Sym(f"{e}.pitch")
    d2 = Add((d, Neg(Mul((_c("iso724.d2_coefficient"), p)))))
    d3 = Add((d, Neg(Mul((_c("iso724.d3_coefficient"), p)))))
    return Mul((Div(Pi(), _n(4)), PowInt(Div(Add((d2, d3)), _n(2)), 2)))


def _resistance(deck: Deck, e: str) -> Expr:
    return Div(_c("cu.rho20"), Sym(f"{e}.area"))


def _adiabatic(deck: Deck) -> Expr:
    return Div(Mul((_c("cu.qc"), Add((_c("cu.beta"), _n(20))))), _c("cu.rho20"))


def _k_factor(deck: Deck, e: str) -> Expr:
    beta = _c("cu.beta")
    ratio = Div(Add((beta, Sym(f"{e}.theta_sc"))), Add((beta, Sym(f"{e}.theta_max"))))
    return Sqrt(Mul((_adiabatic(deck), Ln(ratio))))


def _annulus(power: int, scale: int) -> Callable[[Deck, str], Expr]:
    def build(deck: Deck, e: str) -> Expr:
        outer = Sym(f"{e}.D")
        inner = Add((outer, Neg(Mul((_n(2), Sym(f"{e}.t"))))))
        return Mul((Div(Pi(), _n(scale)), Add((PowInt(outer, power), Neg(PowInt(inner, power))))))
    return build


def _times(constant: str, prop: str) -> Callable[[Deck, str], Expr]:
    return lambda deck, e: Mul((_c(constant), Sym(f"{e}.{prop}")))


def _const_expr(expr: Expr) -> Callable[[Deck, str], Expr]:
    return lambda deck, e: expr


RELATIONS: tuple[Relation, ...] = (
    Relation("bolt.class_ratio", "bolt.", _rec("class_yield_ratio"),
             lambda deck, e: Div(Sym(f"{e}.Rp02_min"), Sym(f"{e}.Rm_min")), Fraction(2, 100)),
    Relation("bolt.proof_load", "bolt.", _rec("Fp"),
             lambda deck, e: Mul((Sym(f"{e}.Sp"), Sym(f"{e}.As"))), Fraction(1, 200)),
    Relation("bolt.stress_area", "bolt.", _rec("As"), _stress_area, Fraction(1, 200)),
    Relation("bolt.yield_order", "bolt.", _rec("Rp02_min"), _rec("Rm_min"), Fraction(0), "le"),
    Relation("breaker.conventional_non_tripping", "mcb.", _rec("I_nt"), _times("iec60898_1.nontrip_factor", "In"),
             Fraction(0)),
    Relation("breaker.conventional_tripping", "mcb.", _rec("I_t"), _times("iec60898_1.trip_factor", "In"), Fraction(0)),
    Relation("cable.conductor_diameter", "cable.", _rec("conductor_diameter"),
             lambda deck, e: Sqrt(Div(Mul((_n(4), Sym(f"{e}.area"))), Pi())), Fraction(1, 200)),
    Relation("cable.insulation_thermal_resistance", "cable.", _rec("T1"),
             lambda deck, e: Mul((Div(Sym(f"{e}.thermal_resistivity"), Mul((_n(2), Pi()))),
                                  Ln(Div(Sym(f"{e}.outer_diameter"), Sym(f"{e}.conductor_diameter"))))),
             Fraction(1, 100)),
    Relation("cable.k_factor", "cable.", _rec("k"), _k_factor, Fraction(1, 100)),
    Relation("cable.outer_diameter", "cable.", _rec("outer_diameter"),
             lambda deck, e: Add((Sym(f"{e}.conductor_diameter"), Mul((_n(2), Sym(f"{e}.insulation"))))),
             Fraction(1, 200)),
    Relation("cable.resistance", "cable.", _rec("R20"), _resistance, Fraction(1, 10), "within"),
    Relation("conductor.resistance_table", "const.iec60228.", _rec("R20_max_table"), _resistance, Fraction(1, 10),
             "within"),
    Relation("copper.adiabatic_constant", "const.cu", _rec("K_table"), lambda deck, e: Sqrt(_adiabatic(deck)),
             Fraction(1, 200)),
    Relation("copper.temperature_coefficient", "const.cu", _rec("alpha20"),
             lambda deck, e: Div(_n(1), Add((_c("cu.beta"), _n(20)))), Fraction(1, 200)),
    Relation("insulation.k_factor_table", "const.pvc", _rec("k_cu_table"), _k_factor, Fraction(1, 100)),
    Relation("material.shear_modulus", "", _rec("G"),
             lambda deck, e: Div(Sym(f"{e}.E"), Mul((_n(2), Add((_n(1), Sym(f"{e}.nu")))))), Fraction(2, 100)),
    Relation("material.yield_order", "", _rec("fy"), _rec("fu"), Fraction(0), "le"),
    Relation("section.area", "chs.", _rec("A"), _annulus(2, 4), Fraction(1, 200)),
    Relation("section.second_moment", "chs.", _rec("I"), _annulus(4, 64), Fraction(1, 200)),
    Relation("thread.minor_diameter_coefficient", "const.iso724", _rec("d3_coefficient"),
             _const_expr(Mul((_n(Fraction(17, 24)), Sqrt(_n(3))))), Fraction(1, 10**6)),
    Relation("thread.pitch_diameter_coefficient", "const.iso724", _rec("d2_coefficient"),
             _const_expr(Mul((_n(Fraction(3, 8)), Sqrt(_n(3))))), Fraction(1, 10**6)),
    Relation("thread.stress_area_table", "const.iso261.", _rec("As_table"), _stress_area, Fraction(1, 200)),
)


def check_deck(deck: Deck, relations: tuple[Relation, ...] = RELATIONS) -> tuple[Finding, ...]:
    """Every finding, sorted by entry. Deterministic."""
    box = {f"{r.entry}.{r.prop}": r.value for r in deck.records}
    entries = sorted({r.entry for r in deck.records})
    findings = [Finding(r.entry, "record.provenance", r.value, r.value, f"{r.prop}: {problem}")
                for r in deck.records if (problem := provenance_problem(r.provenance)) is not None]
    findings += [f for r in deck.records if (f := _check_copy(r, box)) is not None]
    for relation in relations:
        for entry in entries:
            if entry.startswith(relation.applies_to):
                finding = _check(relation, deck, entry, box)
                if finding is not None:
                    findings.append(finding)
    return tuple(sorted(findings, key=lambda f: (f.entry, f.relation, f.message)))


def corrupt(deck: Deck, entry: str, prop: str, factor: Fraction) -> Deck:
    """Test helper: scale one record. tests/test_registry_consistency.py corrupts one record per
    relation and asserts check_deck reports exactly that entry and relation."""
    record = _record(deck, entry, prop)
    lo, hi = sorted((record.value.lo * factor, record.value.hi * factor))
    scaled = replace(record, value=Interval(Fraction(lo), Fraction(hi)))
    return Deck(deck.format, tuple(scaled if r is record else r for r in deck.records))


def flagged_entries(findings: tuple[Finding, ...]) -> frozenset[str]:
    return frozenset(f.entry for f in findings)


def _record(deck: Deck, entry: str, prop: str) -> DeckRecord:
    record = deck.get(entry, prop)
    if record is None:
        raise KeyError(f"the deck has no record {entry}.{prop}")
    return record


def _check(relation: Relation, deck: Deck, entry: str, box: Mapping[str, Interval]) -> Finding | None:
    lhs, rhs = relation.lhs(deck, entry), relation.rhs(deck, entry)
    if not free_syms(lhs) <= box.keys():
        return None
    try:
        left = enclose(lhs, box)
    except EvaluationError as exc:
        zero = Interval(Fraction(0), Fraction(0))
        return Finding(entry, relation.id, zero, zero, f"cannot evaluate {render(lhs)}: {exc}")
    missing = sorted(free_syms(rhs) - box.keys())
    if missing:
        return Finding(entry, relation.id, left, left, f"cannot re-derive {render(lhs)}: no record {', '.join(missing)}")
    try:
        right = enclose(rhs, box)
    except EvaluationError as exc:
        return Finding(entry, relation.id, left, left, f"cannot evaluate {render(rhs)} for {render(lhs)}: {exc}")
    if _holds(relation.kind, relation.rel_tol, left, right):
        return None
    names = free_syms(lhs)
    unit = f" {deck.get(*_split(next(iter(names)))).unit}" if len(names) == 1 else ""
    found = f"{render(lhs)} = {interval_text(left)}{unit}"
    derived = f"{render(rhs)} = {interval_text(right)}"
    tol = decimal(relation.rel_tol)
    message = {
        "eq": f"{found} differs from {derived} by more than relative tolerance {tol}",
        "le": f"{found} exceeds {derived}",
        "within": f"{found} lies outside 1 to 1 + {tol} times {derived}",
    }[relation.kind]
    return Finding(entry, relation.id, left, right, message)


def _check_copy(record: DeckRecord, box: Mapping[str, Interval]) -> Finding | None:
    kind, _, key = record.provenance.partition(":")
    if kind != "derived" or not _PREMISE_KEY.fullmatch(key):
        return None
    name = f"{record.entry}.{record.prop}"
    if key not in box:
        return Finding(record.entry, "record.copy", record.value, record.value,
                       f"cannot re-derive {name}: no record {key}")
    if record.value == box[key]:
        return None
    return Finding(record.entry, "record.copy", record.value, box[key],
                   f"{name} = {interval_text(record.value)} {record.unit} differs from {key} = "
                   f"{interval_text(box[key])}, which it copies")


def _holds(kind: str, tol: Fraction, left: Interval, right: Interval) -> bool:
    """False only when every value in left breaks the relation with every value in right."""
    upper = right.hi + tol * abs(right.hi)
    if kind == "le":
        return left.lo <= upper
    lower = right.lo if kind == "within" else right.lo - tol * abs(right.lo)
    return left.hi >= lower and left.lo <= upper


def _split(name: str) -> tuple[str, str]:
    entry, _, prop = name.rpartition(".")
    return entry, prop
