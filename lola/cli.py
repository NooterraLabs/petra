"""Command line. Untrusted shell: parses arguments, builds evidence sources, prints.

    python -m lola check FILE [--json] [--certs DIR] [--library DIR] [--no-solve] [--deck FILE]
        Elaborate, gather evidence (certs, then library, then solvers unless --no-solve),
        kernel-check, print one verdict per claim plus the "coverage" entry, with each
        footprint. Accepted evidence is written to --certs when given. --deck checks the
        registry against that deck file instead of the one built from the shipped
        registry. --json prints pipeline.Report.to_json():
            {"file": FILE, "design": NAME, "status": OVERALL, "verdicts": [
                {"claim": NAME, "status": "PASS" | "FAIL" | "UNKNOWN",
                 "footprint": [{"tag", "label", "owner", "source"}, ...],
                 "rules": ["R1", ...],
                 "obligations": [what each open item needs, ...]},   non-empty iff UNKNOWN
                ...]}
        Exit code from the overall status (EXIT_CODES): 0 PASS, 1 FAIL, 2 UNKNOWN,
        3 input error (syntax, lowering, ComponentError or an unreadable deck; nothing is
        printed to stdout).
    python -m lola explain FILE
        Print the elaborated statements with hypothesis labels.
    python -m lola verify CERT.json [...]
        Kernel-check certificate files on their own (statement taken from the file), and
        library files, which are certificate envelopes with a "models" list. This is what
        a Lean kernel will reimplement. Exit 0 when the kernel accepts every file (a
        theorem or a refutation), 1 when it rejects one, 3 when a file does not decode.
    python -m lola certify-family FILE --library DIR
        Certify a family design's claims over its whole box and store them in the
        library. Exit 0 when every claim is stored, 1 when one is refuted, 2 when one is
        neither proved nor refuted, 3 when FILE is not a family or does not load.
    python -m lola registry build --out DECK.json
    python -m lola registry check [DECK.json]
        Run the deck consistency checker. With no DECK, check the deck built from the
        shipped registry. Exit 0 when every relation holds, 1 when one fails, 3 when the
        deck does not parse.
    python -m lola gym --episodes N --seed S [--domain NAME ...] [--library DIR]
        Run the baseline agent. Prints one summary line, AgentStats.render():
        "solved k/N episodes (library hits h, families added f)". --domain takes names
        from lola.models.DOMAINS that gym.tasks.GENERATORS covers; default all of them.

A usage error (an unknown subcommand or flag) is an input error too and exits 3. A crash
(an unimplemented elaborator, a bug) prints its traceback and exits 4, so it never reads
as a verdict.

The family benchmark is scripts/bench_family.py, not a subcommand.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Mapping, NoReturn

from . import kernel
from .certs import CertificateError, CertStore, decode_certificate
from .lang import LolaSyntaxError, LoweringError, load_design
from .library import Library, certify_family
from .models.base import ComponentError
from .pipeline import check_design, explain
from .registry import DeckError, build_deck, build_registry, check_deck, read_deck, write_deck
from .solvers import SolverSource
from .verdict import STATUS, Refuted

EXIT_CODES: Mapping[str, int] = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "INPUT_ERROR": 3, "INTERNAL_ERROR": 4}

_INPUT_ERRORS = (LolaSyntaxError, LoweringError, ComponentError, DeckError, OSError)


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, which `lola check` reserves for UNKNOWN."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_CODES["INPUT_ERROR"], f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """Subcommands check, explain, verify, certify-family, registry (build, check) and
    gym, with the flags in the module docstring."""
    from .gym.tasks import GENERATORS

    parser = _Parser(prog="lola", description="verdicts about physical designs as theorems relative to explicit premises")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    check = commands.add_parser("check", help="check a design and print its verdicts")
    check.add_argument("file")
    check.add_argument("--json", action="store_true", help="print the report as JSON")
    check.add_argument("--certs", metavar="DIR", help="certificate directory: read first, accepted evidence written back")
    check.add_argument("--library", metavar="DIR", help="family library to reuse evidence from")
    check.add_argument("--no-solve", action="store_true", help="do not run the solvers")
    check.add_argument("--deck", metavar="FILE", help="registry deck to check against")
    check.set_defaults(run=cmd_check)

    explain_cmd = commands.add_parser("explain", help="print the elaborated statements")
    explain_cmd.add_argument("file")
    explain_cmd.set_defaults(run=cmd_explain)

    verify = commands.add_parser("verify", help="kernel-check certificate files on their own")
    verify.add_argument("certs", nargs="+", metavar="CERT")
    verify.set_defaults(run=cmd_verify)

    family = commands.add_parser("certify-family", help="certify a family design into a library")
    family.add_argument("file")
    family.add_argument("--library", metavar="DIR", required=True)
    family.set_defaults(run=cmd_certify_family)

    registry = commands.add_parser("registry", help="registry deck tools")
    decks = registry.add_subparsers(dest="registry_command", required=True, parser_class=_Parser)
    build = decks.add_parser("build", help="write the deck built from the shipped registry")
    build.add_argument("--out", metavar="DECK", required=True)
    build.set_defaults(run=cmd_registry_build)
    consistency = decks.add_parser("check", help="run the deck consistency checker")
    consistency.add_argument("deck", nargs="?", metavar="DECK")
    consistency.set_defaults(run=cmd_registry_check)

    gym = commands.add_parser("gym", help="run the baseline agent")
    gym.add_argument("--episodes", type=int, required=True)
    gym.add_argument("--seed", type=int, required=True)
    gym.add_argument("--domain", action="append", choices=sorted(GENERATORS), metavar="NAME",
                     help=f"one of {', '.join(sorted(GENERATORS))}; repeat for several")
    gym.add_argument("--library", metavar="DIR")
    gym.set_defaults(run=cmd_gym)
    return parser


def _input_error(exc: BaseException) -> int:
    print(f"lola: {exc}", file=sys.stderr)
    return EXIT_CODES["INPUT_ERROR"]


def cmd_check(args: argparse.Namespace) -> int:
    """Load, check_design, print render() or json.dumps(to_json(), sort_keys=True).
    Returns EXIT_CODES[report status], or EXIT_CODES["INPUT_ERROR"] on LolaSyntaxError,
    LoweringError or ComponentError (message on stderr)."""
    try:
        registry = build_registry()
        design = load_design(args.file, registry)
        deck = read_deck(args.deck) if args.deck else None
        store = CertStore(args.certs) if args.certs else None
        library = Library(args.library) if args.library else None
        sources = tuple(s for s in (store, library, None if args.no_solve else SolverSource()) if s is not None)
        report = check_design(design, registry, sources, sink=store, deck=deck, path=args.file)
    except _INPUT_ERRORS as exc:
        return _input_error(exc)
    print(json.dumps(report.to_json(), sort_keys=True) if args.json else report.render())
    return EXIT_CODES[STATUS[type(report.verdict)]]


def cmd_explain(args: argparse.Namespace) -> int:
    try:
        registry = build_registry()
        text = explain(load_design(args.file, registry), registry)
    except _INPUT_ERRORS as exc:
        return _input_error(exc)
    print(text)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """The statement comes from the file, so a pass says only that the evidence proves
    the statement written there; `lola check` is what ties a statement to a design."""
    worst = 0
    for path in args.certs:
        try:
            cert = _read_certificate(path)
        except (OSError, CertificateError) as exc:
            print(f"{path}: unreadable: {exc}")
            worst = max(worst, EXIT_CODES["INPUT_ERROR"])
            continue
        result = kernel.check(cert.statement, cert.evidence)
        if isinstance(result, kernel.Rejection):
            print(f"{path}: REJECTED {cert.statement_hash} (rule {result.rule}): {result.reason}")
            worst = max(worst, 1)
        else:
            print(f"{path}: {type(result).__name__.lower()} {cert.statement_hash}")
    return worst


def _read_certificate(path: str):
    """A certificate envelope, or a library file (the envelope plus "models")."""
    def unique(pairs: list[tuple[str, object]]) -> dict:
        obj = dict(pairs)
        if len(obj) != len(pairs):
            raise CertificateError("a JSON object repeats a key")
        return obj

    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CertificateError(str(exc)) from None
    if isinstance(obj, dict) and "models" in obj:
        obj = {k: v for k, v in obj.items() if k != "models"}
    return decode_certificate(obj)


def cmd_certify_family(args: argparse.Namespace) -> int:
    try:
        registry = build_registry()
        design = load_design(args.file, registry)
        result = certify_family(design, registry, Library(args.library))
    except (*_INPUT_ERRORS, ValueError) as exc:
        return _input_error(exc)
    for entry in result.stored:
        print(f"stored   {entry.family_key} (shape {entry.shape_hash})")
    for reason in result.skipped:
        print(f"skipped  {reason}")
    if not result.skipped:
        return 0
    refuted = any(isinstance(o, Refuted) for o in result.report.outcomes)
    return EXIT_CODES["FAIL"] if refuted else EXIT_CODES["UNKNOWN"]


def cmd_registry_build(args: argparse.Namespace) -> int:
    try:
        write_deck(build_deck(), args.out)
    except OSError as exc:
        return _input_error(exc)
    print(f"wrote {args.out}")
    return 0


def cmd_registry_check(args: argparse.Namespace) -> int:
    """registry.check_deck on the given deck, or on registry.build_deck() when none is
    given. Prints each flagged relation."""
    try:
        deck = read_deck(args.deck) if args.deck else build_deck()
    except (DeckError, OSError) as exc:
        return _input_error(exc)
    findings = check_deck(deck)
    for f in findings:
        print(f"{f.entry}: {f.relation}: {f.message} (lhs {f.lhs.lo}..{f.lhs.hi}, rhs {f.rhs.lo}..{f.rhs.hi})")
    print(f"{len(deck.records)} records, {len(findings)} findings")
    return 1 if findings else 0


def cmd_gym(args: argparse.Namespace) -> int:
    """gym.run_episodes(domains, args.episodes, args.seed, args.library) and print
    stats.render(). Returns 0 when it ran, whatever the solve rate."""
    from .gym import GENERATORS, run_episodes

    domains = tuple(args.domain) if args.domain else tuple(sorted(GENERATORS))
    print(run_episodes(domains, args.episodes, args.seed, args.library).render())
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except Exception:  # an uncaught crash would exit 1, which reads as FAIL
        traceback.print_exc()
        return EXIT_CODES["INTERNAL_ERROR"]
