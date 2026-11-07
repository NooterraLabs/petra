"""The electronics deck's gate (docs/electronics_dc.md, the gate). Tooling: nothing here
changes a verdict. `python scripts/electronics_gate.py` runs it and writes
docs/electronics_gate.md.

  1. Decidedness: every generated design is PASS or FAIL, never UNKNOWN.
  2. Claims on target: each claim lands on the side its margin aimed at, proved for
     target "pass" and refuted for target "fail".
  3. Makeability: every FAIL carries a refutation, the witness point.
  4. Certificates: for a sample of the designs, the kernel accepts every certificate the
     check wrote, and the design re-checked from those certificates alone gets the same
     verdict.
  5. Planted faults: every one caught (FAIL) and named (one of its modes refuted).
"""
from __future__ import annotations

import shutil
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Iterable

from ... import kernel
from ...certs import CertStore, load_certificate
from ...lang import parse_design
from ...pipeline import check_design
from ...registry import Registry, build_registry
from ...solvers import SolverSource
from ...verdict import STATUS
from ..base import ClaimOrigin
from . import faults as F
from .generate import Generated, generate

OUTCOME = {"Discharged": "pass", "WithinMargin": "pass", "Refuted": "fail", "Open": "open"}


@dataclass
class Assessed:
    name: str
    kind: str
    status: str
    redraws: int
    witnessed: bool                                     # every refuted requirement carries its point
    modes: dict[str, str]                               # mode -> "pass" | "fail" | "open", the worst over requirements
    claims: dict[str, tuple[str, str]]                  # claim -> (target, outcome)
    needs: list[str] = field(default_factory=list)      # what an open requirement needs
    certificates: str | None = None                     # None: not re-checked; "ok"; else what failed


def outcomes(report) -> tuple[dict[str, str], dict[str, str], bool, list[str]]:
    """(mode -> worst state, claim -> worst state, every refutation has its point, the open needs)."""
    rank = {"pass": 0, "open": 1, "fail": 2}
    modes: dict[str, str] = {}
    claims: dict[str, str] = {}
    witnessed = True
    needs: list[str] = []
    for o in report.outcomes:
        kind = type(o).__name__
        if kind not in OUTCOME:
            continue
        req = o.requirement if kind == "Open" else o.obligation.requirement
        state = OUTCOME[kind]
        mode = req.mode.id.split(".", 1)[1]
        if rank[state] >= rank[modes.get(mode, "pass")]:
            modes[mode] = state
        if isinstance(req.origin, ClaimOrigin):
            claim = req.origin.claim
            if rank[state] >= rank[claims.get(claim, "pass")]:
                claims[claim] = state
        witnessed &= kind != "Refuted" or o.refutation is not None
        if kind == "Open":
            needs.append(str(o.needs[0]) if o.needs else kind)
    return modes, claims, witnessed, needs


def certificates(text: str, registry: Registry, status: str) -> str:
    """Check the design writing its certificates to a temporary directory, verify each with
    the kernel, re-check the design from them alone, and say "ok" or what failed."""
    root = tempfile.mkdtemp(prefix="electronics-certs-")
    try:
        store = CertStore(root)
        design = parse_design(text, "gate.petra", registry)
        check_design(design, registry, (SolverSource(),), sink=store)
        paths = store.paths()
        if not paths:
            return "no certificate written"
        held = [(p.name, load_certificate(p)) for p in paths]
        rejected = [name for name, c in held if isinstance(kernel.check(c.statement, c.evidence), kernel.Rejection)]
        if rejected:
            return f"the kernel rejected {rejected}"
        again = STATUS[type(check_design(design, registry, (store,)).verdict)]
        return "ok" if again == status else f"re-checked from {len(paths)} certificates as {again}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def assess(g: Generated, registry: Registry, with_certificates: bool) -> Assessed:
    report = check_design(parse_design(g.text, "gate.petra", registry), registry, (SolverSource(),))
    status = STATUS[type(report.verdict)]
    modes, claims, witnessed, needs = outcomes(report)
    out = Assessed(g.name, g.kind, status, g.redraws, witnessed, modes,
                   {c.name: (c.target, claims.get(c.name, "absent")) for c in g.claims}, needs)
    if with_certificates:
        out.certificates = certificates(g.text, registry, status)
    return out


def chunk(args: tuple[int, int, int, int]) -> list[dict]:
    """A worker's slice of the stream: (seed, start, count, every), re-checking the
    certificates of every `every`-th design (none for 0)."""
    seed, start, count, every = args
    registry = build_registry()
    return [asdict(assess(g, registry, every > 0 and (start + i) % every == 0))
            for i, g in enumerate(generate(count, seed, registry, start))]


@dataclass
class Summary:
    n: int
    seed: int
    statuses: Counter
    by_kind: Counter                    # (kind, status)
    refuted: Counter                    # mode -> designs that fail it
    undecided: list[dict]
    unwitnessed: list[str]
    claims: int
    off_target: list[dict]
    certified: int
    certificate_failures: list[dict]
    redraws: int
    faults: list[F.Caught]


def summarise(rows: Iterable[dict], seed: int, faults: list[F.Caught]) -> Summary:
    rows = list(rows)
    return Summary(
        len(rows), seed, Counter(r["status"] for r in rows), Counter((r["kind"], r["status"]) for r in rows),
        Counter(m for r in rows for m, s in r["modes"].items() if s == "fail"),
        [{"name": r["name"], "kind": r["kind"], "status": r["status"], "needs": r["needs"]}
         for r in rows if r["status"] not in ("PASS", "FAIL")],
        [r["name"] for r in rows if r["status"] == "FAIL" and not r["witnessed"]],
        sum(len(r["claims"]) for r in rows),
        [{"name": r["name"], "claim": c, "target": t, "outcome": o} for r in rows for c, (t, o) in r["claims"].items()
         if (t, o) not in (("pass", "pass"), ("fail", "fail"))],
        sum(r["certificates"] is not None for r in rows),
        [{"name": r["name"], "certificates": r["certificates"]} for r in rows if r["certificates"] not in (None, "ok")],
        sum(r["redraws"] for r in rows), faults)


def failed(s: Summary) -> bool:
    applied = {c.fault for c in s.faults}
    return bool(s.undecided or s.unwitnessed or s.off_target or s.certificate_failures
                or not all(c.caught and c.is_named for c in s.faults) or any(f.name not in applied for f in F.FAULTS))


def render(s: Summary) -> str:
    kinds = sorted({k for k, _ in s.by_kind})
    caught = sum(c.caught for c in s.faults)
    named = sum(c.caught and c.is_named for c in s.faults)
    lines = [
        "# Electronics deck gate (generated by `python scripts/electronics_gate.py`; do not edit)",
        "",
        f"Stream seed {s.seed}: {s.n} generated boards across {len(kinds)} kinds "
        f"(petra/models/electronics/generate.py), drawn in {s.n + s.redraws} tries. Measured on this run.",
        "",
        "| Gate item | Result |",
        "|---|---|",
        f"| 1. Decidedness | {s.n - len(s.undecided)} of {s.n} PASS or FAIL; {len(s.undecided)} UNKNOWN |",
        f"| 2. Claims on target | {s.claims - len(s.off_target)} of {s.claims} claims land on the side their margin "
        "aimed at |",
        f"| 3. Makeability | {s.statuses['FAIL'] - len(s.unwitnessed)} of {s.statuses['FAIL']} FAILs carry a witness |",
        f"| 4. Certificates | {s.certified - len(s.certificate_failures)} of {s.certified} sampled designs re-check: "
        "the kernel accepts every certificate, and the certificates alone give the same verdict |",
        f"| 5. Planted faults | {caught} of {len(s.faults)} caught (FAIL), {named} named by the fault's mode |",
        "",
        "## Verdicts by kind",
        "",
        "| Kind | PASS | FAIL | other |",
        "|---|---|---|---|",
    ]
    for kind in kinds:
        other = sum(n for (k, st), n in s.by_kind.items() if k == kind and st not in ("PASS", "FAIL"))
        lines.append(f"| {kind} | {s.by_kind[(kind, 'PASS')]} | {s.by_kind[(kind, 'FAIL')]} | {other} |")
    lines += ["", "## Designs failing each mode", "", "| Mode | Designs |", "|---|---|"]
    lines += [f"| {mode} | {n} |" for mode, n in sorted(s.refuted.items())]
    lines += ["", "## Planted faults", "", "| Fault | Modes | Planted | Caught | Named |", "|---|---|---|---|---|"]
    for fault in F.FAULTS:
        mine = [c for c in s.faults if c.fault == fault.name]
        lines.append(f"| {fault.name}: {fault.defect} | {', '.join(sorted(fault.modes))} | {len(mine)} | "
                     f"{sum(c.caught for c in mine)} | {sum(c.caught and c.is_named for c in mine)} |")
    for title, items in (("Undecided designs", s.undecided), ("FAILs without a witness", s.unwitnessed),
                         ("Claims off target", s.off_target), ("Certificate failures", s.certificate_failures)):
        if items:
            lines += ["", f"## {title}", ""] + [f"- {item}" for item in items[:50]]
    missed = [c for c in s.faults if not (c.caught and c.is_named)]
    if missed:
        lines += ["", "## Faults missed", ""] + [f"- {c}" for c in missed]
    return "\n".join(lines) + "\n"
