"""The steel deck's exhaustiveness gate (docs/steel_connections.md §9 items 4 to 9). Tooling:
nothing here changes a verdict. `python scripts/steel_gate.py` runs it and writes
docs/steel_gate.md and docs/steel_gate_log.jsonl.

  4. Decidedness: every generated design is PASS or FAIL, never UNKNOWN or MARGINAL.
  5. Twins: per required mode, the deck's outcome and the twin's utilisation agree
     (Discharged with u <= 1, Refuted with u > 1), and they owe the same modes.
  6. Manufactured faults: every one caught (not PASS) and named (a fault mode refuted or open).
  7. Breaker: no design the deck passes and the twin fails, within the budget.
  8. Makeability: every FAIL carries a refutation, the witness point.
  9. Report: every design's calculation package (package.py) re-checks: the kernel accepts
     every certificate, every cited statement has one, and the design re-checked from
     the certificates alone gets the same verdict.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Iterable

from ...lang import parse_design
from ...pipeline import check_design
from ...registry import Registry, build_registry
from ...solvers import SolverSource
from ...verdict import STATUS
from . import faults as F
from . import ic
from . import package as P
from .generate import Generated, generate

SLACK = 1e-6
"""The twin computes in floats; the deck decides exactly. Within SLACK of 1 both readings stand."""
CERTIFIED = {"weld": ic.WELD_LOSS, "weld_base_metal": ic.WELD_LOSS}
"""Modes whose deck capacity on a weld line loaded out of its plane is the kernel-certified lower
bound of the instantaneous center, which may give up ic.WELD_LOSS of the twin's C. A deck FAIL
with the twin that far below 1 is the certificate's margin, not a disagreement. A deck PASS is
held to SLACK in every mode."""


@dataclass
class Assessed:
    name: str
    kind: str
    expected: str
    status: str
    toleranced: bool
    free: bool
    witnessed: bool                                   # a FAIL with a refutation in hand
    deck: dict[str, str]                              # mode -> "pass" | "fail" | "open"
    twin: dict[str, float] | None = None
    twin_error: str | None = None
    disagreements: list[tuple[str, str, float | None]] = field(default_factory=list)
    package: str | None = None                        # None: not packaged; "ok"; else what failed
    cyclic: bool = False                              # its gate case names cycles (Appendix 3)


def deck_outcomes(report) -> tuple[dict[str, str], bool]:
    modes: dict[str, str] = {}
    witnessed = False
    rank = {"pass": 0, "open": 1, "fail": 2}
    for o in report.outcomes:
        kind = type(o).__name__
        if kind == "Waived":
            continue
        req = o.requirement if kind == "Open" else o.obligation.requirement
        mode = req.mode.id.split(".", 1)[1]
        state = {"Discharged": "pass", "Refuted": "fail", "Open": "open", "WithinMargin": "pass"}[kind]
        witnessed |= kind == "Refuted" and o.refutation is not None
        if rank[state] >= rank[modes.get(mode, "pass")]:
            modes[mode] = state
    return modes, witnessed


def compare(deck: dict[str, str], twin: dict[str, float]) -> list[tuple[str, str, float | None]]:
    """(mode, deck state, twin utilisation) wherever the two disagree."""
    out = []
    for mode in sorted(set(deck) | set(twin)):
        state, u = deck.get(mode), twin.get(mode)
        if state is None or u is None:
            out.append((mode, state or "absent", u))
        elif state == "pass" and u > 1 + SLACK or state == "fail" and u < 1 - CERTIFIED.get(mode, SLACK) or state == "open":
            out.append((mode, state, u))
    return out


def assess(g: Generated, registry: Registry, with_twin: bool = True) -> Assessed:
    design = parse_design(g.text, "gate.petra", registry)
    report = check_design(design, registry, (SolverSource(),))
    deck, witnessed = deck_outcomes(report)
    out = Assessed(g.name, g.kind, g.expected, STATUS[type(report.verdict)], g.toleranced, g.free, witnessed, deck,
                   cyclic=g.cycles is not None)
    if with_twin:
        from . import twin
        try:
            out.twin = twin.utilisations_of(design, registry, "gate")["c1"]
        except Exception as e:  # the twin is tooling: its failure is a finding, not a crash
            out.twin_error = f"{type(e).__name__}: {e}"
        else:
            out.disagreements = compare(deck, out.twin)
    return out


def packaged(g: Generated, registry: Registry, status: str) -> str:
    """Write the design's calculation package to a temporary directory, re-check it, and
    say "ok" or what failed, a limit state that holds but reads a utilisation above 1
    included."""
    root = tempfile.mkdtemp(prefix="steel-package-")
    try:
        pkg = P.write_package(g.text, root, registry)
        again = P.recheck(pkg, registry)
        if pkg.status != status:
            return f"packaged as {pkg.status}, checked as {status}"
        if pkg.over:
            return f"a limit state that holds reads above 1: {'; '.join(pkg.over)}"
        if not again.holds(status):
            return f"rejected {list(again.rejected)}, missing {list(again.missing)}, re-checked as {again.status}"
        return "ok"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def chunk(args: tuple[int, int, int, bool, bool]) -> list[dict]:
    """A worker's slice of the stream: (seed, start, count, with_twin, with_packages)."""
    seed, start, count, with_twin, with_packages = args
    registry = build_registry()
    rows = []
    for g in generate(count, seed, registry, start):
        a = assess(g, registry, with_twin)
        if with_packages:
            a.package = packaged(g, registry, a.status)
        rows.append(asdict(a))
    return rows


@dataclass
class Summary:
    n: int
    seed: int
    statuses: Counter
    expected: Counter                     # (expected, status)
    by_kind: Counter                      # (kind, status)
    undecided: list[dict]
    unwitnessed: list[str]
    unexpected: list[dict]                # the verdict is not the one the generator aimed at
    twin_errors: list[dict]
    disagreements: list[dict]
    toleranced: int
    free: int
    twinned: int
    packaged: int
    package_failures: list[dict]
    faults: list[F.Caught]
    breaker: list[dict]
    budget: int
    cyclic: Counter                       # status of the designs under a cyclic load


def summarise(rows: Iterable[dict], seed: int, faults: list[F.Caught], breaker: list[dict], budget: int) -> Summary:
    rows = list(rows)
    return Summary(
        len(rows), seed, Counter(r["status"] for r in rows), Counter((r["expected"], r["status"]) for r in rows),
        Counter((r["kind"], r["status"]) for r in rows),
        [r for r in rows if r["status"] not in ("PASS", "FAIL")],
        [r["name"] for r in rows if r["status"] == "FAIL" and not r["witnessed"]],
        [{k: r[k] for k in ("name", "kind", "expected", "status", "toleranced", "free")}
         for r in rows if r["status"] in ("PASS", "FAIL") and r["status"] != r["expected"]],
        [{"name": r["name"], "error": r["twin_error"]} for r in rows if r["twin_error"]],
        [{"name": r["name"], "kind": r["kind"], "toleranced": r["toleranced"], "disagreements": r["disagreements"]}
         for r in rows if r["disagreements"]],
        sum(r["toleranced"] for r in rows), sum(r["free"] for r in rows),
        sum(r["twin"] is not None or r["twin_error"] is not None for r in rows),
        sum(r["package"] is not None for r in rows),
        [{"name": r["name"], "package": r["package"]} for r in rows if r["package"] not in (None, "ok")],
        faults, breaker, budget, Counter(r["status"] for r in rows if r.get("cyclic")))


def render(s: Summary) -> str:
    kinds = sorted({k for k, _ in s.by_kind})
    found = [b for b in s.breaker if b["false_pass"]]
    caught = sum(c.caught for c in s.faults)
    named = sum(c.caught and c.is_named for c in s.faults)
    mode_disagree = Counter(d[0] for row in s.disagreements for d in row["disagreements"])
    lines = [
        "# Steel deck gate (generated by `python scripts/steel_gate.py`; do not edit)",
        "",
        f"Stream seed {s.seed}: {s.n} generated connections across {len(kinds)} kinds, {s.toleranced} with a toleranced "
        f"length, {s.free} drawn without the detailer's rules, {sum(s.cyclic.values())} under a cyclic load (Appendix 3; "
        f"{s.cyclic['PASS']} PASS, {s.cyclic['FAIL']} FAIL, "
        f"{sum(n for st, n in s.cyclic.items() if st not in ('PASS', 'FAIL'))} other). Each load sits at 1 - 0.02 k or "
        "1 + 0.02 k of the deck's governing strength, k in [1, 4] (petra/models/steel/generate.py).",
        "",
        "| Gate item | Result |",
        "|---|---|",
        f"| 4. Decidedness | {s.n - len(s.undecided)} of {s.n} PASS or FAIL; {len(s.undecided)} UNKNOWN or MARGINAL |",
        f"| 5. Twins | {s.twinned - len(s.disagreements) - len(s.twin_errors)} of {s.twinned} agree on every mode; "
        f"{len(s.disagreements)} disagree; {len(s.twin_errors)} twin errors |" if s.twinned else "| 5. Twins | not run |",
        f"| 6. Manufactured faults | {caught} of {len(s.faults)} caught, {named} named by the fault's mode |",
        f"| 7. Breaker | {len(s.breaker)} runs, {s.budget} deck evaluations each; {len(found)} found a false PASS |",
        f"| 8. Makeability | {s.statuses['FAIL'] - len(s.unwitnessed)} of {s.statuses['FAIL']} FAILs carry a witness |",
        f"| 9. Report | {s.packaged - len(s.package_failures)} of {s.packaged} calculation packages re-check (every "
        "certificate accepted by the kernel, every cited statement present, the verdict reproduced from the "
        "certificates alone, no limit state that holds read above 1) |",
        "",
        "## Verdicts by kind",
        "",
        "| Kind | PASS | FAIL | other |",
        "|---|---|---|---|",
    ]
    for kind in kinds:
        other = sum(n for (k, st), n in s.by_kind.items() if k == kind and st not in ("PASS", "FAIL"))
        lines.append(f"| {kind} | {s.by_kind[(kind, 'PASS')]} | {s.by_kind[(kind, 'FAIL')]} | {other} |")
    lines += ["", "Expected (from the deck's own utilisations and geometry) against the verdict: " +
              ", ".join(f"{e} as {st}: {n}" for (e, st), n in sorted(s.expected.items())) + "." +
              (f" The {len(s.unexpected)} designs decided otherwise are in the log." if s.unexpected else ""), ""]
    if mode_disagree:
        lines += ["## Twin disagreements by mode", "", "| Mode | Designs |", "|---|---|"]
        lines += [f"| {m} | {n} |" for m, n in mode_disagree.most_common()]
        lines.append("")
    lines += ["## Manufactured faults", "", "| Fault | Designs | Caught | Named |", "|---|---|---|---|"]
    for name in dict.fromkeys(c.fault for c in s.faults):
        cs = [c for c in s.faults if c.fault == name]
        lines.append(f"| {name} | {len(cs)} | {sum(c.caught for c in cs)} | {sum(c.caught and c.is_named for c in cs)} |")
    lines += ["", "## Breaker runs", "", "| Start | Kind | Evaluations | Accepted | Oracle's worst u at the best passing point "
              "| Mode | False PASS |", "|---|---|---|---|---|---|---|"]
    for b in s.breaker:
        lines.append(f"| {b['base']} | {b['kind']} | {b['evaluations']} | {b['accepted']} | {b['best']:.4f} | "
                     f"{b['best_mode']} | {len(b['false_pass'])} |")
    lines += ["", "Every run, disagreement and fault is in docs/steel_gate_log.jsonl.", ""]
    return "\n".join(lines)


def log_lines(s: Summary) -> list[str]:
    out = [json.dumps({"undecided": u}) for u in s.undecided]
    out += [json.dumps({"unexpected": u}) for u in s.unexpected]
    out += [json.dumps({"twin_error": e}) for e in s.twin_errors]
    out += [json.dumps({"package_failure": f}) for f in s.package_failures]
    out += [json.dumps({"disagreement": d}) for d in s.disagreements]
    out += [json.dumps({"fault": asdict(c)}) for c in s.faults]
    out += [json.dumps({"breaker": b}) for b in s.breaker]
    return out
