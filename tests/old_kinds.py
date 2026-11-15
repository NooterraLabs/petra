"""Two helpers for the tests of the old path, which go with it (docs/old_path_removal.md).

A design of a kind with no deck of rules gets no pass from any way into a check: it reads
UNKNOWN with exit code 2 and the reason that its kind has no deck (plan step 1.1a,
tests/test_no_wrong_pass.py). `no_deck` is how a test that pinned an old-path PASS through
`petra check` pins that now.

The Python checker's own report of such a design is still what the tests of its internals
read. `python_report` gives it, as `petra.check_file` did until 2026-11-14. No status of
that report is a verdict.
"""
import json
from pathlib import Path
from typing import Any

REASON = "no deck of rules has a part of kind "
"""How the reason starts (petra.verify.no_deck)."""


def no_deck(out: str) -> bool:
    """Whether what `petra check` printed, as text or as JSON, is UNKNOWN with the reason
    that the design's kind has no deck of rules, and says nowhere on its first lines that
    the design passes."""
    if out.lstrip().startswith("{"):
        report = json.loads(out)
        return report["status"] == "UNKNOWN" and report["reason"].startswith(REASON) and "python" not in report
    lines = out.splitlines()
    return lines[0].endswith(": UNKNOWN") and lines[1].startswith("reason     " + REASON) and not any("PASS" in line for line in lines[:6])


def python_report(path: str | Path, *, card: str | Path | None = None, certs: str | Path | None = None, library: Any = None, solve: bool = True) -> Any:
    """The Python checker's report of the design at `path` against its card (pipeline.Report),
    or the grid's own for a design of a deck, with no kernel run."""
    from petra import grid, wellformed
    from petra.certs import CertStore
    from petra.lang import load_design
    from petra.pipeline import check_design
    from petra.registry import build_registry
    from petra.solvers import SolverSource

    registry = build_registry()
    design = load_design(path, registry, card)
    rules = grid.owner(design)
    if rules is not None:
        return grid.check(design, rules)[0]
    wellformed.require(design, registry)
    store = CertStore(certs) if certs is not None else None
    sources = tuple(s for s in (store, library, SolverSource() if solve else None) if s is not None)
    return check_design(design, registry, sources, sink=store, path=str(path))


def python_status(card: str, text: str) -> str:
    """The Python checker's own status of a pair given as its two texts: PASS, FAIL, UNKNOWN
    or MARGINAL. It is what the repair search and the loop built on it predict and search
    by, and no verdict."""
    from petra.lang import parse_design
    from petra.pipeline import check_design
    from petra.registry import build_registry
    from petra.solvers import SolverSource
    from petra.verdict import STATUS

    registry = build_registry()
    return STATUS[type(check_design(parse_design(card, text, "<design>", registry), registry, (SolverSource(),)).verdict)]
