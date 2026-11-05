"""The mutation lever: valid certificate fixtures, and operators that break them.

Owner: seam M. This module is the single source of truth behind
tests/test_kernel_mutations.py. It builds one valid certificate per rule and per
evidence kind (including refutations, and the R3 lemma under both a proof and a
refutation, since check proves it over different boxes), and a set of mutation operators
that are each guaranteed to invalidate a certificate. The test file asserts the fixtures
check and the mutants are rejected; run this module directly to self-check both.

A fixture is stored as an envelope, the exact shape examples/bolt_tension.cert.json uses
and that call site 3 in docs/design.md checks on its own:

    statement = decode_statement(env["statement"])
    assert statement_hash(statement) == env["statement_hash"]
    result = check(statement, decode_evidence(env["evidence"]))

`verify_envelope` runs precisely that protocol, so a tampered statement is caught by the
hash before the kernel runs, and tampered evidence is caught by the kernel.

Every operator is total: for each fixture it applies to, it provably destroys validity.
Operators that could leave a certificate valid (scaling a Farkas ray, moving a split
point to another interior point) are deliberately absent.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from fractions import Fraction as Q
from typing import Any, Callable

from lola.kernel import (
    Add,
    Const,
    DecodeError,
    DefinedHyp,
    DefinedRange,
    Evidence,
    Leaf,
    Matrix,
    Neg,
    PowInt,
    RangeHyp,
    Refutation,
    Rejection,
    Split,
    Statement,
    Sym,
    Theorem,
    check,
    decode_evidence,
    decode_statement,
    encode_evidence,
    encode_statement,
    statement_hash,
)
from lola.kernel.rules.r1_linear import FarkasRay, FeasiblePoints, LinearFeasible
from lola.kernel.rules.r2_definite import GramPositiveDefinite, GramTerm, LDLFactor, NegativeDirection
from lola.kernel.rules.r3_hypercircle import (
    ComponentBound,
    Hypercircle,
    HypercircleFields,
    HypercircleViolation,
    MinimizerBound,
    MinimizerComponent,
    QuadraticProblem,
)
from lola.kernel.rules.r4_enclosure import AllNonpositive, Enclosure, PointWitness
from lola.kernel.rules.r5_moment import MomentBound, MomentConstraint, MomentDual, RandomVar
from lola.kernel.rules.r6_scenario import Arithmetic, BinomialTail

ENVELOPE_FORMAT = "lola-cert/0"
KERNEL_VERSION = "lola-kernel/0"


def _c(v) -> Const:
    return Const(Q(v))


def _sorted_hyps(hyps: tuple) -> tuple:
    return tuple(sorted(hyps, key=lambda h: h.sym))


# ---------------------------------------------------------------------------
# One valid certificate per rule and evidence kind. Numbers are hand-derived
# (the derivations are in docs/design.md and tests/test_rules.py).
# ---------------------------------------------------------------------------

_PAIR = Matrix(1, 2, ((0, 0, Q(1)), (0, 1, Q(1))))


def _r1_proof() -> tuple[Statement, Evidence]:
    """x0 + x1 = F, 0 <= xi <= 3, for F in [2, 4]. Feasible at each vertex."""
    goal = LinearFeasible(A=_PAIR, b=(Sym("F"),), lower=(_c(0), _c(0)), upper=(_c(3), _c(3)))
    st = Statement(hyps=(RangeHyp("F", Q(2), Q(4), "in:F"),), goal=goal)
    return st, Evidence(FeasiblePoints(x=((Q(1), Q(1)), (Q(2), Q(2)))))


def _r1_refutation() -> tuple[Statement, Evidence]:
    """Same system for F in [2, 7]: at F = 7 the sum caps at 6, so it is infeasible."""
    goal = LinearFeasible(A=_PAIR, b=(Sym("F"),), lower=(_c(0), _c(0)), upper=(_c(3), _c(3)))
    st = Statement(hyps=(RangeHyp("F", Q(2), Q(7), "in:F"),), goal=goal)
    return st, Evidence(FarkasRay(point=(("F", Q(7)),), y=(Q(1),)))


_IDENTITY = Matrix(2, 2, ((0, 0, Q(1)), (1, 1, Q(1))))
_ONES = Matrix(2, 1, ((0, 0, Q(1)), (1, 0, Q(1))))
_UNIT_LOWER = Matrix(2, 2, ((0, 0, Q(1)), (1, 0, Q(-1, 3)), (1, 1, Q(1))))


def _stiffness(lam_hi) -> Statement:
    goal = GramPositiveDefinite(dim=2, terms=(GramTerm(Sym("E"), _IDENTITY), GramTerm(Neg(Sym("lam")), _ONES)))
    return Statement(hyps=_sorted_hyps((RangeHyp("E", Q(1), Q(2), "in:E"), RangeHyp("lam", Q(0), Q(lam_hi), "in:lam"))), goal=goal)


def _r2_proof() -> tuple[Statement, Evidence]:
    """E I - lam 1 1^T, eigenvalues E and E - 2 lam, positive for E in [1,2], lam in [0,1/4]."""
    body = LDLFactor(reference_weights=(Q(1), Q(-1, 4)), L=_UNIT_LOWER, d=(Q(3, 4), Q(2, 3)))
    return _stiffness(Q(1, 4)), Evidence(body)


def _r2_refutation() -> tuple[Statement, Evidence]:
    """For lam up to 1, at E = 1, lam = 1 the matrix [[0,-1],[-1,0]] is indefinite."""
    return _stiffness(1), Evidence(NegativeDirection(point=(("E", Q(1)), ("lam", Q(1))), v=(Q(1), Q(1))))


_PROBLEM = QuadraticProblem(B=_PAIR, f=(Sym("F"),), w=(_c(1), _c(3)))
_EXACT = HypercircleFields(s=((Q(3), Q(1)), (Q(6), Q(2))), u=((Q(3),), (Q(6),)))


def _r3_proof() -> tuple[Statement, Evidence]:
    """min s0^2 + 3 s1^2 s.t. s0 + s1 = F, F in [4,8]: s* = (3F/4, F/4), energy 3F^2/4 <= 48."""
    bounds = (
        ComponentBound(index=0, scale=_c(1), lo=_c(3), hi=_c(6)),
        ComponentBound(index=1, scale=_c(4), lo=None, hi=_c(8)),
    )
    goal = MinimizerBound(problem=_PROBLEM, bounds=bounds, energy_hi=_c(48))
    return Statement(hyps=(RangeHyp("F", Q(4), Q(8), "in:F"),), goal=goal), Evidence(Hypercircle(_EXACT))


def _r3_refutation() -> tuple[Statement, Evidence]:
    """Claim s*_0 <= 5, but at F = 8 the minimiser has s*_0 = 6."""
    goal = MinimizerBound(problem=_PROBLEM, bounds=(ComponentBound(index=0, scale=_c(1), lo=None, hi=_c(5)),), energy_hi=None)
    st = Statement(hyps=(RangeHyp("F", Q(4), Q(8), "in:F"),), goal=goal)
    return st, Evidence(HypercircleViolation(point=(("F", Q(8)),), s=(Q(6), Q(2)), u=(Q(6),), which=0))


def _r3_lemma() -> tuple[Statement, Evidence]:
    """q = s*_0 of the same problem lies in [3,6], so q - 7 <= 0. An R4 goal over an R3 lemma."""
    st = Statement(
        hyps=_sorted_hyps((RangeHyp("F", Q(4), Q(8), "in:F"), DefinedHyp("q", MinimizerComponent(_PROBLEM, 0, _c(1))))),
        goal=AllNonpositive(exprs=(Add((Sym("q"), _c(-7))),)),
    )
    ev = Evidence(body=Enclosure(partition=Leaf()), defined=(DefinedRange("q", Q(3), Q(6), _EXACT),))
    return st, ev


def _r3_lemma_refutation() -> tuple[Statement, Evidence]:
    """The same q exceeds 5 at F = 8, where s* = (6, 2) and u* = 6. The lemma is proved at
    that point, with the exact field once per vertex of the point box, so q = 6 there."""
    st = Statement(
        hyps=_sorted_hyps((RangeHyp("F", Q(4), Q(8), "in:F"), DefinedHyp("q", MinimizerComponent(_PROBLEM, 0, _c(1))))),
        goal=AllNonpositive(exprs=(Add((Sym("q"), _c(-5))),)),
    )
    at_8 = HypercircleFields(s=((Q(6), Q(2)), (Q(6), Q(2))), u=((Q(6),), (Q(6),)))
    return st, Evidence(PointWitness(point=(("F", Q(8)),), which=0), defined=(DefinedRange("q", Q(6), Q(6), at_8),))


def _quadratic_partition() -> Split:
    """A partition fine enough to beat the dependency problem in x^2 - x - 1/10 over [0,1]."""
    def split(at, left=Leaf(), right=Leaf()) -> Split:
        return Split("x", Q(at), left, right)

    return split(Q(1, 2), split(Q(1, 4)), split(Q(3, 4), Leaf(), split(Q(7, 8), Leaf(), split(Q(15, 16)))))


def _r4_proof() -> tuple[Statement, Evidence]:
    """x^2 - x - 1/10 <= 0 over [0,1]; true (max of x^2 - x is 0) but needs a fine partition."""
    goal = AllNonpositive(exprs=(Add((PowInt(Sym("x"), 2), Neg(Sym("x")), _c(Q(-1, 10)))),))
    st = Statement(hyps=(RangeHyp("x", Q(0), Q(1), "in:x"),), goal=goal)
    return st, Evidence(Enclosure(partition=_quadratic_partition()))


def _r4_refutation() -> tuple[Statement, Evidence]:
    """x - 1 <= 0 over [0,2] is false at x = 2."""
    goal = AllNonpositive(exprs=(Add((Sym("x"), _c(-1))),))
    st = Statement(hyps=(RangeHyp("x", Q(0), Q(2), "in:x"),), goal=goal)
    return st, Evidence(PointWitness(point=(("x", Q(2)),), which=0))


def _r5_proof() -> tuple[Statement, Evidence]:
    """P(X > C) for X on [0,40] with mean 10 and C in [36,40]. Markov g = x/36 gives 10/36 <= 3/10."""
    goal = MomentBound(
        random=(RandomVar("x", Sym("Lo"), Sym("Hi")),),
        moments=(MomentConstraint(Sym("x"), Sym("M"), Sym("M")),),
        fail=Add((Sym("x"), Neg(Sym("C")))),
        p=Q(3, 10),
    )
    hyps = _sorted_hyps((RangeHyp("C", Q(36), Q(40), "in:C"), RangeHyp("Hi", Q(40), Q(40), "in:Hi"), RangeHyp("Lo", Q(0), Q(0), "in:Lo"), RangeHyp("M", Q(10), Q(10), "in:M")))
    return Statement(hyps=hyps, goal=goal), Evidence(MomentDual(y0=Q(0), y=(Q(1, 36),), partition=Split("x", Q(36), Leaf(), Leaf())))


def _r6_proof() -> tuple[Statement, Evidence]:
    """0 failures in 300 trials at eps = 1/100: tail 0.99^300 ~ 0.0490 <= 1/20."""
    goal = BinomialTail(n=_c(300), k=_c(0), eps=_c(Q(1, 100)), beta=_c(Q(1, 20)))
    return Statement(hyps=(), goal=goal), Evidence(Arithmetic())


@dataclass(frozen=True)
class Fixture:
    name: str
    rule: str
    kind: str                       # "theorem" or "refutation"
    statement: Statement
    evidence: Evidence
    lb_path: tuple | None = None    # a load-bearing rational in the evidence JSON
    vec_path: tuple | None = None   # a vector in the evidence JSON whose length is checked
    has_split: bool = False

    def envelope(self) -> dict:
        st_json = encode_statement(self.statement)
        return {
            "format": ENVELOPE_FORMAT,
            "kernel": KERNEL_VERSION,
            "statement_hash": statement_hash(self.statement),
            "statement": st_json,
            "evidence": encode_evidence(self.evidence),
            "producer": {"source": "tests.mutations", "lola": "0"},
        }


def _fixtures() -> tuple[Fixture, ...]:
    r1p_s, r1p_e = _r1_proof()
    r1r_s, r1r_e = _r1_refutation()
    r2p_s, r2p_e = _r2_proof()
    r2r_s, r2r_e = _r2_refutation()
    r3p_s, r3p_e = _r3_proof()
    r3r_s, r3r_e = _r3_refutation()
    r3l_s, r3l_e = _r3_lemma()
    r3w_s, r3w_e = _r3_lemma_refutation()
    r4p_s, r4p_e = _r4_proof()
    r4r_s, r4r_e = _r4_refutation()
    r5p_s, r5p_e = _r5_proof()
    r6p_s, r6p_e = _r6_proof()
    return (
        Fixture("r1_feasible", "R1", "theorem", r1p_s, r1p_e, lb_path=("body", "x", 0, 0), vec_path=("body", "x")),
        Fixture("r1_farkas", "R1", "refutation", r1r_s, r1r_e),
        Fixture("r2_ldl", "R2", "theorem", r2p_s, r2p_e, lb_path=("body", "d", 0), vec_path=("body", "d")),
        Fixture("r2_negative_direction", "R2", "refutation", r2r_s, r2r_e),
        Fixture("r3_hypercircle", "R3", "theorem", r3p_s, r3p_e, lb_path=("body", "fields", "s", 0, 0), vec_path=("body", "fields", "s")),
        Fixture("r3_violation", "R3", "refutation", r3r_s, r3r_e),
        Fixture("r3_lemma", "R4", "theorem", r3l_s, r3l_e, lb_path=("defined", 0, "proof", "s", 0, 0), vec_path=("defined", 0, "proof", "s")),
        Fixture("r3_lemma_witness", "R4", "refutation", r3w_s, r3w_e, lb_path=("defined", 0, "proof", "s", 0, 0), vec_path=("defined", 0, "proof", "s")),
        Fixture("r4_enclosure", "R4", "theorem", r4p_s, r4p_e, has_split=True),
        Fixture("r4_point_witness", "R4", "refutation", r4r_s, r4r_e),
        Fixture("r5_moment_dual", "R5", "theorem", r5p_s, r5p_e, lb_path=("body", "y", 0), vec_path=("body", "y"), has_split=True),
        Fixture("r6_binomial", "R6", "theorem", r6p_s, r6p_e),
    )


FIXTURES: tuple[Fixture, ...] = _fixtures()
BY_NAME: dict[str, Fixture] = {f.name: f for f in FIXTURES}


# ---------------------------------------------------------------------------
# Verifying an envelope the way a standalone checker (design.md call site 3) does.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HashMismatch:
    """The stored statement_hash does not match the statement, so the file is rejected
    before the kernel runs. Not a kernel result."""

    expected: str
    actual: str


def verify_envelope(env: dict) -> Any:
    """Theorem | Refutation | Rejection | HashMismatch, or raises DecodeError.

    decode_statement and decode_evidence raise DecodeError on malformed or non-canonical
    JSON; a statement whose hash does not match returns HashMismatch; otherwise the
    kernel's own CheckResult is returned.
    """
    statement = decode_statement(env["statement"])
    digest = statement_hash(statement)
    if digest != env["statement_hash"]:
        return HashMismatch(env["statement_hash"], digest)
    return check(statement, decode_evidence(env["evidence"]))


# ---------------------------------------------------------------------------
# JSON surgery helpers.
# ---------------------------------------------------------------------------

_INT = re.compile(r"-?(0|[1-9][0-9]*)")
_RAT = re.compile(r"-?(0|[1-9][0-9]*)(/[1-9][0-9]*)?")


def _get(obj: Any, path: tuple) -> Any:
    for p in path:
        obj = obj[p]
    return obj


def _set(obj: Any, path: tuple, value: Any) -> None:
    for p in path[:-1]:
        obj = obj[p]
    obj[path[-1]] = value


def _find_first(obj: Any, want: Callable[[str], bool]) -> list | None:
    """Path to the first string leaf matching `want`, depth first in document order."""
    if isinstance(obj, dict):
        for key in obj:
            if isinstance(obj[key], str) and want(obj[key]):
                return [key]
            sub = _find_first(obj[key], want)
            if sub is not None:
                return [key] + sub
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and want(item):
                return [i]
            sub = _find_first(item, want)
            if sub is not None:
                return [i] + sub
    return None


def _is_int_rational(s: str) -> bool:
    return bool(_INT.fullmatch(s))


def _is_rational(s: str) -> bool:
    return bool(_RAT.fullmatch(s))


def _bump(s: str) -> str:
    return str(int(s) + 1)


def _non_canonical(s: str) -> str:
    """A different spelling of the same value that parse_q must reject."""
    if "/" in s:
        n, d = s.split("/")
        return f"{int(n) * 2}/{int(d) * 2}"
    return f"{s}/1"


def _find_split(obj: Any) -> Any:
    if isinstance(obj, dict):
        if obj.get("t") == "split":
            return obj
        for v in obj.values():
            found = _find_split(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_split(v)
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------------------
# Mutation operators. Each is total on the fixtures it applies to.
# ---------------------------------------------------------------------------

REJECTION = "rejection"
DECODE_ERROR = "decode_error"
HASH_MISMATCH = "hash_mismatch"


@dataclass(frozen=True)
class Operator:
    name: str
    why: str
    expect: str
    applies: Callable[[Fixture], bool]
    apply: Callable[[Fixture, dict], dict]


def _perturb(fix: Fixture, env: dict) -> dict:
    s = _get(env["evidence"], fix.lb_path)
    _set(env["evidence"], fix.lb_path, _bump(s) if "/" not in s else f"{Q(s) + 1}")
    return env


def _drop(fix: Fixture, env: dict) -> dict:
    _get(env["evidence"], fix.vec_path).pop()
    return env


def _duplicate(fix: Fixture, env: dict) -> dict:
    vec = _get(env["evidence"], fix.vec_path)
    vec.append(copy.deepcopy(vec[-1]))
    return env


def _change_rule_tag(fix: Fixture, env: dict) -> dict:
    body = env["evidence"]["body"]
    body["t"] = "arithmetic" if body["t"] == "ldl" else "ldl"
    return env


def _unknown_key(fix: Fixture, env: dict) -> dict:
    env["statement"]["unexpected_key"] = 0
    return env


def _non_canonical_rational(fix: Fixture, env: dict) -> dict:
    path = _find_first(env["statement"], _is_rational)
    _set(env["statement"], tuple(path), _non_canonical(_get(env["statement"], tuple(path))))
    return env


def _rename_split(fix: Fixture, env: dict) -> dict:
    _find_split(env["evidence"])["sym"] = "__renamed__"
    return env


def _edit_statement_byte(fix: Fixture, env: dict) -> dict:
    path = _find_first(env["statement"], _is_int_rational)
    _set(env["statement"], tuple(path), _bump(_get(env["statement"], tuple(path))))
    return env


def _point_outside(fix: Fixture, env: dict) -> dict:
    coordinate = env["evidence"]["body"]["point"][0]
    (hyp,) = [h for h in env["statement"]["hyps"] if h["t"] == "range_hyp" and h["sym"] == coordinate[0]]
    coordinate[1] = str(Q(hyp["hi"]) + 1)
    return env


def _foreign_evidence(fix: Fixture, env: dict) -> dict:
    if fix.rule == "R1":
        env["evidence"]["body"] = {"t": "enclosure", "partition": {"t": "leaf"}}
    else:
        env["evidence"]["body"] = {"t": "feasible_points", "x": [["0"]]}
    return env


OPERATORS: tuple[Operator, ...] = (
    Operator(
        "perturb_load_bearing_rational",
        "a +1 to a feasible point, an LDL pivot, an admissible field or a dual weight breaks the exact equality or bound the proof rests on",
        REJECTION,
        lambda f: f.lb_path is not None,
        _perturb,
    ),
    Operator(
        "drop_vector_entry",
        "a vector one entry short no longer has the length the rule's shape check requires",
        REJECTION,
        lambda f: f.vec_path is not None,
        _drop,
    ),
    Operator(
        "duplicate_vector_entry",
        "a vector with a duplicated entry is longer than the vertices or terms it must match",
        REJECTION,
        lambda f: f.vec_path is not None,
        _duplicate,
    ),
    Operator(
        "change_rule_tag",
        "retagging the evidence body as another rule's evidence leaves the wrong fields, which the strict codec rejects",
        DECODE_ERROR,
        lambda f: True,
        _change_rule_tag,
    ),
    Operator(
        "add_unknown_json_key",
        "an extra key means the object is not exactly the term's fields, which the strict codec rejects",
        DECODE_ERROR,
        lambda f: True,
        _unknown_key,
    ),
    Operator(
        "non_canonical_rational",
        "a non-reduced or n/1 rational has no canonical spelling, so parse_q rejects it and the file has no meaning",
        DECODE_ERROR,
        lambda f: True,
        _non_canonical_rational,
    ),
    Operator(
        "rename_split_symbol",
        "a split on a symbol absent from the cell is not strictly inside any range, so the partition walk rejects it",
        REJECTION,
        lambda f: f.has_split,
        _rename_split,
    ),
    Operator(
        "edit_stored_statement_byte",
        "a changed statement no longer hashes to the stored statement_hash, so the file is rejected before the kernel runs",
        HASH_MISMATCH,
        lambda f: True,
        _edit_statement_byte,
    ),
    Operator(
        "move_point_outside_box",
        "a refutation point one past its RangeHyp's upper end is not a point the premises admit, so check rejects it before any lemma or rule runs",
        REJECTION,
        lambda f: f.kind == "refutation",
        _point_outside,
    ),
    Operator(
        "foreign_rule_evidence",
        "a well-formed evidence body of another rule is not evidence for this goal's rule",
        REJECTION,
        lambda f: True,
        _foreign_evidence,
    ),
)


def write_fixtures(directory) -> list:
    """Write <name>.cert.json for every fixture as canonical UTF-8 text with LF endings."""
    import json
    from pathlib import Path

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for fix in FIXTURES:
        text = json.dumps(fix.envelope(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        path = out / f"{fix.name}.cert.json"
        path.write_text(text + "\n", encoding="utf-8", newline="\n")
        written.append(path)
    return written


def _self_check() -> int:
    problems = []
    for fix in FIXTURES:
        result = verify_envelope(fix.envelope())
        want = Theorem if fix.kind == "theorem" else Refutation
        if not isinstance(result, want):
            problems.append(f"fixture {fix.name}: expected {want.__name__}, got {result!r}")
    fired = {op.name: 0 for op in OPERATORS}
    for fix in FIXTURES:
        for op in OPERATORS:
            if not op.applies(fix):
                continue
            env = op.apply(fix, copy.deepcopy(fix.envelope()))
            try:
                result = verify_envelope(env)
            except DecodeError:
                result = DECODE_ERROR
            got = (
                DECODE_ERROR if result == DECODE_ERROR
                else HASH_MISMATCH if isinstance(result, HashMismatch)
                else REJECTION if isinstance(result, Rejection)
                else f"NOT REJECTED: {type(result).__name__}"
            )
            if got != op.expect:
                problems.append(f"{fix.name} x {op.name}: expected {op.expect}, got {got}")
            else:
                fired[op.name] += 1
    for name, count in fired.items():
        if count == 0:
            problems.append(f"operator {name} never fired")
    for p in problems:
        print("FAIL:", p)
    print(f"{len(FIXTURES)} fixtures, {len(OPERATORS)} operators, {sum(fired.values())} mutants checked")
    return 1 if problems else 0


if __name__ == "__main__":
    import sys

    sys.exit(_self_check())
