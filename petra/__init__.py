"""Petra: verdicts about physical designs as theorems relative to explicit premises.

    import petra
    result = petra.check(text)  # plain data; a FAIL's "repair" names the inputs to change
    report = petra.check_file("examples/truss_pass.petra")
    print(report.render())
    report.verdict            # petra.Pass | petra.Fail | petra.Unknown | petra.Marginal
    report.verdict.footprint  # every non-proved premise the verdict used
    report.findings           # each obligation's numbers in the design's units (readout.py)

petra/docs/api.md documents this API and the JSON `petra check --json` prints, and
`petra docs api` prints it from any install. `petra docs` lists every document, the
language reference among them.

Trust layout:
    petra.kernel     mathematics only, stdlib only, the part a Lean kernel replaces
    petra.models     physics elaborators, trusted, each one a validated_model premise
    petra.lang, petra.ir, petra.units, petra.registry (model, constants, catalog),
    petra.premises, petra.coverage, petra.verdict, petra.pipeline     trusted plumbing
    everything else (solvers, library, certs, registry.deck and registry.consistency,
    gym, bench, readout, envelope, cli) is untrusted: a bug there costs an UNKNOWN, never
    a false PASS.
"""
from __future__ import annotations

from pathlib import Path

from .certs import CertStore
from .lang import load_design, parse_design
from .library import Library, certify_family
from .pipeline import Report, check_design, explain
from .registry import build_registry
from .solvers import SolverSource
from .verdict import Fail, Marginal, Pass, Unknown, Verdict

__version__ = "0.1.0"


def check(text: str, *, path: str = "<text>", repair: bool = True) -> dict:
    """Check a design given as text, with the shipped registry and the solvers, and return
    plain data that json.dumps takes as it is: the report's JSON (petra/docs/api.md) with a
    "repair" key, which on a FAIL names the inputs that lower the governing check (repair.py)
    and is None otherwise, or with `repair=False`. A design that does not lower gives
    {"file", "status": "INPUT_ERROR", "error"} instead of raising."""
    from .repair import check_text

    return check_text(text, path, build_registry(), (SolverSource(),), moves=repair).to_json()


def check_file(path: str | Path, *, certs: str | Path | None = None, library: Library | None = None, solve: bool = True) -> Report:
    """Convenience shell over check_design: default registry, evidence sources in the
    order certs -> library -> solvers, accepted evidence recorded into `certs` when given."""
    registry = build_registry()
    design = load_design(path, registry)
    store = CertStore(certs) if certs is not None else None
    sources = tuple(s for s in (store, library, SolverSource() if solve else None) if s is not None)
    return check_design(design, registry, sources, sink=store, path=str(path))
