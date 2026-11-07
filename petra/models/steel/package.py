"""Calculation packages for the steel deck (docs/steel_connections.md §9 item 9). Tooling:
nothing here changes a verdict.

`write_package(text, out, registry)` checks a design and leaves in `out`:

  design.petra   the design as checked;
  certs/        one kernel certificate per obligation the deck settled (the theorem's or
                the refutation's evidence, with the statement it proves), named by the
                statement's hash;
  report.md     the calculation: per connection, per required limit state, the method and
                its source, the validity rows and premises, each check's demand, available
                strength and utilisation in every load case, the outcome, and the hash of
                the statement behind it.

Two commands re-check a package without trusting it. `petra verify certs/*.json` has the
kernel re-check every certificate on its own. `petra check --certs certs --no-solve
design.petra` re-elaborates the design, finds each obligation's certificate by the hash of
the fresh statement and reproduces the verdict from the package alone: that ties the
statements to the design, so neither the report's numbers nor its hashes are trusted.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ... import kernel
from ...certs import CertStore, load_certificate
from ...lang import parse_design
from ...pipeline import Report, check_design
from ...registry import Registry
from ...solvers import SolverSource
from ...verdict import STATUS
from . import calc
from .domain import required
from .lower import KIND_SPECS
from .vocab import MODELS, MODES

STATES = {"Discharged": "holds", "Refuted": "FAILS", "Open": "open", "WithinMargin": "holds, within its margin", "Waived": "waived"}


@dataclass(frozen=True)
class Package:
    root: Path
    status: str
    hashes: tuple[str, ...]          # every statement hash the report cites (obligations and validity)
    report: Report


def _hashes(outcome) -> tuple[str | None, tuple[str, ...]]:
    kind = type(outcome).__name__
    if kind == "Discharged":
        return outcome.theorem.statement_hash, tuple(t.statement_hash for t in outcome.validity)
    if kind == "Refuted":
        return outcome.refutation.statement_hash, tuple(t.statement_hash for t in outcome.validity)
    if kind == "WithinMargin":
        return (outcome.theorem.statement_hash if outcome.theorem else None), tuple(t.statement_hash for t in outcome.validity)
    return None, ()


def _number(x: float) -> str:
    return "inf" if x == float("inf") else f"{x:.4g}"


def render(design, report: Report, registry: Registry, text: str) -> tuple[str, tuple[str, ...]]:
    outcomes = {}
    for o in report.outcomes:
        req = o.requirement if type(o).__name__ in ("Open", "Waived") else o.obligation.requirement
        outcomes[(req.subject[0], req.mode.id)] = o
    cited: list[str] = []
    lines = [f"# Calculation package: {design.name}", "",
             f"Verdict: **{STATUS[type(report.verdict)]}**, by the Petra kernel over every load case and every value in each "
             "stated range.", "",
             "Re-check it without trusting this file: `petra verify certs/*.json` re-checks each certificate; `petra check "
             "--certs certs --no-solve design.petra` re-derives every statement from the design and reproduces the verdict "
             "from the certificates alone.", "",
             "## Design", "", "```", text.rstrip(), "```", ""]
    for name, component in design.components.items():
        if component.kind not in KIND_SPECS:
            continue
        conn = calc.connection(design, name, registry)
        lines += [f"## Connection {name} ({component.kind}, {conn.attrs['basis'].upper()})", ""]
        for mode in required(conn, design):
            fm = MODES.get(mode)
            outcome = outcomes.get((name, fm.id)) if fm else None
            state = STATES.get(type(outcome).__name__, "not checked") if outcome is not None else "not checked"
            lines.append(f"### {mode}: {state}")
            lines.append("")
            if fm in MODELS:
                spec = MODELS[fm]
                lines.append(f"Method: {spec.form}. Source: {spec.source}.")
                lines.append("")
                lines.append(f"Premises: {spec.validity}.")
                for row in spec.rows:
                    lines.append(f"- validity row `{row.id}`: {row.text}")
                for limit in spec.unchecked:
                    lines.append(f"- not checked: {limit}")
                lines.append("")
            for case in design.loads:
                try:
                    values = calc.values(conn, design, registry, mode, case)
                except KeyError:
                    values = []
                if not values:
                    continue
                lines += [f"Load case `{case}`:", "", "| Check | Demand | Available | Unit | Utilisation |", "|---|---|---|---|---|"]
                for v in values:
                    u = "excused" if v.excused else _number(v.utilisation)
                    lines.append(f"| {v.what} | {_number(v.demand)} | {_number(v.capacity)} | {v.unit} | {u} |")
                lines.append("")
            if outcome is not None:
                claim, validity = _hashes(outcome)
                if claim:
                    cited.append(claim)
                    lines.append(f"Statement `{claim}`: certificate certs/{claim.split(':', 1)[1]}.json")
                for h in validity:
                    cited.append(h)
                    lines.append(f"Validity statement `{h}`: certificate certs/{h.split(':', 1)[1]}.json")
                if type(outcome).__name__ == "Refuted":
                    point = ", ".join(f"{k} = {float(v):.6g}" for k, v in sorted(outcome.refutation.point))
                    lines.append(f"Witness (SI units): {point}")
                if type(outcome).__name__ == "Open":
                    lines.append("Open: " + "; ".join(str(n) for n in outcome.needs))
                lines.append("")
    return "\n".join(lines) + "\n", tuple(dict.fromkeys(cited))


def write_package(text: str, out: Path, registry: Registry) -> Package:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "design.petra"
    path.write_text(text, encoding="utf-8", newline="\n")
    design = parse_design(text, str(path), registry)
    report = check_design(design, registry, (SolverSource(),), sink=CertStore(out / "certs"), path=str(path))
    body, cited = render(design, report, registry, text)
    (out / "report.md").write_text(body, encoding="utf-8", newline="\n")
    return Package(out, STATUS[type(report.verdict)], cited, report)


@dataclass(frozen=True)
class Recheck:
    certificates: int
    rejected: tuple[str, ...]        # files the kernel refused, with its reason
    missing: tuple[str, ...]         # hashes the report cites with no certificate file
    status: str                      # the verdict re-derived from the design and the certificates alone

    def holds(self, status: str) -> bool:
        return not self.rejected and not self.missing and self.status == status


def recheck(package: Package, registry: Registry) -> Recheck:
    """What `petra verify certs/*.json` and `petra check --certs certs --no-solve design.petra`
    do, in process: the kernel re-checks every certificate, every cited hash has its file,
    and the design re-checked from the certificates alone gets the package's verdict."""
    store = CertStore(package.root / "certs")
    rejected = []
    for path in store.paths():
        cert = load_certificate(path)
        result = kernel.check(cert.statement, cert.evidence)
        if isinstance(result, kernel.Rejection):
            rejected.append(f"{path.name}: {result.reason}")
    names = {p.stem for p in store.paths()}
    missing = tuple(h for h in package.hashes if h.split(":", 1)[1] not in names)
    path = package.root / "design.petra"
    design = parse_design(path.read_text(encoding="utf-8"), str(path), registry)
    again = check_design(design, registry, (store,), path=str(path))
    return Recheck(len(names), tuple(rejected), missing, STATUS[type(again.verdict)])
