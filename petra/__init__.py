"""Petra: verdicts about physical designs as theorems relative to explicit premises.

    import petra
    result = petra.check(card, design)  # plain data: "status" is the kernel's verdict
    checked = petra.check_file("examples/deck/lap_pass.petra")  # against examples/deck/lap_pass.card
    print(checked.text())
    checked.status            # the kernel's verdict: PASS, PASS_WAIVED, FAIL or UNKNOWN
    checked.reason            # for a design of a kind with no deck of rules: why it reads UNKNOWN

The verdict of a design is the kernel's (petra/verify.py). The models, the Python checker
(petra.kernel), the solvers and the classes below are the old path, which decides nothing:
petra.check_design gives its report, and no status of that report is a verdict.

petra/docs/api.md documents this API and the JSON `petra check --json` prints, and
`petra docs api` prints it from any install. `petra docs` lists every document, the
language reference among them.

Trust layout:
    petra.kernel     mathematics only, stdlib only, the part a Lean kernel replaces
    petra.models     physics elaborators, trusted, each one a validated_model premise
    petra.lang, petra.ir, petra.units, petra.registry (model, constants, catalog),
    petra.premises, petra.coverage, petra.verdict, petra.pipeline     trusted plumbing
    everything else (solvers, library, certs, registry.deck and registry.consistency,
    readout, envelope, cli) is untrusted: a bug there costs an UNKNOWN, never
    a false PASS.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .library import Library
    from .pipeline import Report

__version__ = "0.1.2"

_API = {"CertStore": "certs", "load_design": "lang", "parse_design": "lang", "Library": "library",
        "certify_family": "library", "Report": "pipeline", "check_design": "pipeline", "explain": "pipeline",
        "build_registry": "registry", "SolverSource": "solvers", "Fail": "verdict", "Marginal": "verdict",
        "Pass": "verdict", "Unknown": "verdict", "Verdict": "verdict"}
"""Each name of the API and the submodule that defines it. A name is imported when first
read, and so is a submodule such as petra.kernel, so `petra mcp` answers its handshake
without loading the language, the models, or the solvers with numpy and scipy."""

__all__ = ["check", "check_file", *_API]


def __getattr__(name: str) -> Any:
    if name in _API:
        value = getattr(importlib.import_module(f".{_API[name]}", __name__), name)
    else:
        try:
            value = importlib.import_module(f".{name}", __name__)
        except ModuleNotFoundError as exc:
            if exc.name != f"{__name__}.{name}":
                raise
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    globals()[name] = value
    return value


def check(card: str, design: str, *, path: str = "<design>", repair: bool = True) -> dict:
    """Check a design against a card, both given as text, with the shipped registry and the
    solvers, and return plain data that json.dumps takes as it is: the report's JSON
    (petra/docs/api.md) with a "repair" key, which on a FAIL names the inputs that lower
    the governing check (repair.py) and is None otherwise, or with `repair=False`. A pair
    that does not lower gives {"file", "status": "INPUT_ERROR", "error"} instead of
    raising. The status is the verdict of petra-verify: with no kernel to run, or one whose
    answer cannot be taken, this raises petra.verify.NoVerdict."""
    from .registry import build_registry
    from .repair import check_text
    from .solvers import SolverSource

    return check_text(card, design, path, build_registry(), (SolverSource(),), moves=repair).to_json()


def check_file(path: str | Path, *, card: str | Path | None = None, certs: str | Path | None = None,
               library: Library | None = None, solve: bool = True) -> Any:
    """`check` of the design at `path` against `card`, the .card file beside it when none is
    named, with evidence sources in the order certs -> library -> solvers and accepted
    evidence recorded into `certs` when given. Returns the checked pair (repair.Checked, or
    grid.Checked for a design of a deck of rules): `status` is the kernel's verdict,
    `reason` says why a design whose kinds have no deck of rules reads UNKNOWN, `to_json()`
    is what `petra check --json` prints and `text()` what `petra check` prints. `report` is
    the working behind it, which decides nothing: the grid's report for a design of a deck,
    and the Python checker's for one of the models' kinds.

    Raises what the pair raises when it does not read or lower (lang.LolaSyntaxError,
    lang.LoweringError, models.base.ComponentError, OSError), and petra.verify.NoVerdict
    when there is no kernel to run or its answer cannot be taken."""
    from .certs import CertStore
    from .files import read_pair
    from .registry import build_registry
    from .repair import check_text
    from .solvers import SolverSource

    asked, text = read_pair(path, card)
    store = CertStore(certs) if certs is not None else None
    sources = tuple(s for s in (store, library, SolverSource() if solve else None) if s is not None)
    return check_text(asked, text, str(path), build_registry(), sources, sink=store, moves=False, card_path=None if card is None else str(card),
                      raises=True)
