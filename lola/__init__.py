"""LoLa: verdicts about physical designs as theorems relative to explicit premises.

    import lola
    report = lola.check_file("examples/truss_pass.lola")
    print(report.render())
    report.verdict            # lola.Pass | lola.Fail | lola.Unknown
    report.verdict.footprint  # every non-proved premise the verdict used

Trust layout:
    lola.kernel     mathematics only, stdlib only, the part a Lean kernel replaces
    lola.models     physics elaborators, trusted, each one a validated_model premise
    lola.lang, lola.ir, lola.units, lola.registry (model, constants, catalog),
    lola.premises, lola.coverage, lola.verdict, lola.pipeline     trusted plumbing
    everything else (solvers, library, certs, registry.deck and registry.consistency,
    gym, bench, cli) is untrusted: a bug there costs an UNKNOWN, never a false PASS.
"""
from __future__ import annotations

from pathlib import Path

from .certs import CertStore
from .lang import load_design, parse_design
from .library import Library, certify_family
from .pipeline import Report, check_design, explain
from .registry import build_registry
from .solvers import SolverSource
from .verdict import Fail, Pass, Unknown, Verdict

__version__ = "0.1.0"


def check_file(path: str | Path, *, certs: str | Path | None = None, library: Library | None = None, solve: bool = True) -> Report:
    """Convenience shell over check_design: default registry, evidence sources in the
    order certs -> library -> solvers, accepted evidence recorded into `certs` when given."""
    registry = build_registry()
    design = load_design(path, registry)
    store = CertStore(certs) if certs is not None else None
    sources = tuple(s for s in (store, library, SolverSource() if solve else None) if s is not None)
    return check_design(design, registry, sources, sink=store, path=str(path))
