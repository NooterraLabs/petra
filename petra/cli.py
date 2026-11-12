"""Command line. Untrusted shell: parses arguments, builds evidence sources, prints.

    python -m petra check FILE [--card CARD] [--json] [--certs DIR] [--library DIR] [--no-solve] [--deck FILE]
        FILE is a design and CARD the card it answers, the .card file beside FILE when
        --card is left out; explain, envelope and certify-family take the same two.
        Elaborate, gather evidence (certs, then library, then solvers unless --no-solve),
        kernel-check, print one verdict per claim plus the "coverage" entry, with each
        footprint. Accepted evidence is written to --certs when given. --deck checks the
        registry against that deck file instead of the one built from the shipped
        registry. Under each refuted obligation the text gives the governing term's demand,
        capacity and utilisation in the design's units, and its counterexample as decimals
        in those units. On a FAIL, unless --no-solve, the lines after the governing lines
        name the moves that lower the governing check, best first (petra/repair.py). The
        `card` and `design` lines give the SHA-256 of each text, and the `kernel` line the
        word of petra-verify (petra/verify.py): how many of the proofs it checked, or that
        none is here to run. A proof it rejects exits 4. --json prints
        pipeline.Report.to_json() with "card", "hashes", "kernel" and "repair", the moves
        or null (`petra docs api`):
            {"file": FILE, "design": NAME, "status": OVERALL, "repair": REPAIR | null, "verdicts": [
                {"claim": NAME, "status": "PASS" | "FAIL" | "UNKNOWN" | "MARGINAL",
                 "footprint": [{"tag", "label", "owner", "source", "version"?}, ...],
                 "rules": ["R1", ...],
                 "needs": [what each open item needs, ...],    non-empty iff UNKNOWN
                 "margins": [{"requirement", "proved", "margin": "proved" | "undecided"
                              | "within", "point"?}, ...],   claims with a margin
                 "obligations": [readout.Finding.to_json(), ...]},   one per outcome
                ...]}
        Exit code from the overall status (EXIT_CODES): 0 PASS, 1 FAIL, 2 UNKNOWN,
        5 MARGINAL (a claim with a margin is proved, and a certified point lies within
        its margin of its bound), 6 PASS_WAIVED (a design checked against a deck of rules
        passes, and a cell rests on a waiver: the JSON lists each such waiver under
        "waived"), 3 input error (syntax, lowering,
        ComponentError or an unreadable deck; nothing is printed to stdout).
    python -m petra explain FILE
        Print the elaborated statements with hypothesis labels.
    python -m petra envelope FILE --input NAME --from QTY --to QTY [--at QTY]
                                 [--resolution QTY] [--max-probes N] [--library DIR] [--json]
        Find the widest interval of one input (or param) around an anchor over which
        every obligation that depends on it is proved, by bisecting the design's checks
        (petra/envelope.py), with at most N checks (default 64). A quantity is a number
        and a unit, such as "-20 degC" or -20degC; the text prints in the unit of --from
        (else --to, else --at), the JSON in exact SI. Without --at, the anchor is the
        middle of the input's stated range, or the low end of the probe range when the
        design does not pass at the middle. The exit code is that of the worse of
        the anchor's status and the status of the obligations that do not depend on the
        input ("elsewhere"): 0 when both pass, so an envelope over a design that fails
        elsewhere does not exit 0. 3 for an input error such as an unknown input, a range
        in the wrong unit or an anchor whose design does not lower.
    python -m petra verify CERT.json [...]
        Kernel-check certificate files on their own (statement taken from the file), and
        library files, which are certificate envelopes with a "models" list. This is what
        a Lean kernel will reimplement. Exit 0 when the kernel accepts every file (a
        theorem or a refutation), 1 when it rejects one, 3 when a file does not decode.
    python -m petra certify-family FILE --library DIR
        Certify a family design's claims over its whole box and store them in the
        library. A proved claim is stored even when a certified point lies within its
        margin, and is then listed as "margin". Exit 0 when every claim is stored and
        none is within its margin, 5 when every claim is stored and one is within its
        margin, 1 when one is refuted, 2 when one is otherwise not stored (neither proved
        nor refuted, or waived), 3 when FILE is not a family or does not load.
    python -m petra registry build --out DECK.json
    python -m petra registry check [DECK.json]
        Run the deck consistency checker. With no DECK, check the deck built from the
        shipped registry. Exit 0 when every relation holds, 1 when one fails, 3 when the
        deck does not parse.
    python -m petra registry recall ID [FILE ...] [--json]
        Print each design whose verdicts rest on the registry entry ID (an entry, a premise
        key, a common name or an id prefix), with its status, each such claim's status and
        the premises it rests on with the version each was checked at (petra/recall.py).
        A FILE is a .petra design (checked now), a saved `petra check --json` report (a
        premise checked at an older version is marked) or a directory of .petra files;
        default examples/. Exit 0 when every file was read, 3 for an unknown ID or a file
        that could not be read (the rest are still printed).
    python -m petra registry list [PREFIX]
        Print every registry id a design can name, one line each: what it is, and the
        common names that stand for it (A325 for bolt_group.120). With PREFIX, the ids and
        common names that start with it, in any case; 3 when none does.
    python -m petra kinds [DOMAIN|KIND] [--all] [--json]
        With no argument, print each domain and its kinds. With DOMAIN or KIND, or with
        --all for every kind, print each kind's load and claim forms and its attribute
        lines, required and optional, with their units, registry prefixes and meanings
        (petra/teach.py). --json prints every kind unless DOMAIN or KIND names some. 3 for
        an unknown name, or a name with --all.
    python -m petra new KIND [--name NAME]
        Print a complete design of KIND to start from, its canonical example with the
        component renamed to NAME. 3 for an unknown kind or a name the design cannot take.
    python -m petra docs [NAME]
        Print the document NAME: readme, reference (the language), api (the Python API
        and the JSON) or skill (a SKILL.md for coding agents). With no NAME, list them.
        3 for an unknown name.
    python -m petra mcp [--budget SECONDS]
        Serve check, kinds, new, registry_list and docs to an MCP client, JSON-RPC over
        stdin and stdout, until stdin closes (petra/mcp.py). A tool call that runs longer
        than the budget is stopped and says so. Exit 0.
    python -m petra --version
        Print the version.

A usage error (an unknown subcommand or flag) is an input error too and exits 3. A crash
(an unimplemented elaborator, a bug) prints its traceback and exits 4, so it never reads
as a verdict. When the reader closes stdout early, as `petra check FILE | head` does, the
subcommand stops writing and exits 141 without a traceback.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import re
import stat
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, NoReturn

if TYPE_CHECKING:
    from .units import Quantity

EXIT_CODES: Mapping[str, int] = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "INPUT_ERROR": 3, "INTERNAL_ERROR": 4, "MARGINAL": 5,
                                 "PASS_WAIVED": 6, "BROKEN_PIPE": 141}
"""PASS_WAIVED: a design checked against a deck of rules passes, and a cell rests on a
waiver (grid.PASS_WAIVED). BROKEN_PIPE: the reader closed stdout before Petra finished
writing. 141 is 128 plus SIGPIPE's number, the status a shell reports for a command that a
closed pipe stopped."""


def _input_errors() -> tuple[type[Exception], ...]:
    """The exceptions that are input errors. A command imports what it uses when it runs,
    so that `petra mcp` starts without the language, the models, the kernel or the solvers."""
    from .lang import LolaSyntaxError, LoweringError
    from .models.base import ComponentError
    from .registry import DeckError

    return (LolaSyntaxError, LoweringError, ComponentError, DeckError, OSError)


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, which `petra check` reserves for UNKNOWN."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_CODES["INPUT_ERROR"], f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """Subcommands check, explain, envelope, verify, certify-family, registry (build,
    check, recall, list), kinds, new, docs and mcp, with the flags in the module
    docstring."""
    from . import __version__

    parser = _Parser(prog="petra", description="verdicts about physical designs as theorems relative to explicit premises",
                     formatter_class=argparse.RawDescriptionHelpFormatter,
                     epilog="Coding agents: `petra docs skill` prints a SKILL.md on designing, checking and repairing\n"
                            "with Petra, and `petra mcp` serves Petra's tools to an MCP client over stdio.\n"
                            "The README, the language reference, the Python API and that skill come with Petra:\n"
                            "`petra docs` lists them, and `petra docs NAME` prints one.")
    parser.add_argument("--version", action="version", version=f"petra {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    def design_file(command: argparse.ArgumentParser) -> None:
        command.add_argument("file", help="the design, a .petra file")
        command.add_argument("--card", metavar="FILE", help="the card the design answers; default the .card file beside the design")

    check = commands.add_parser("check", help="check a design against its card and print its verdicts")
    design_file(check)
    check.add_argument("--json", action="store_true", help="print the report as JSON")
    check.add_argument("--certs", metavar="DIR", help="certificate directory: read first, accepted evidence written back")
    check.add_argument("--library", metavar="DIR", help="family library to reuse evidence from")
    check.add_argument("--no-solve", action="store_true", help="do not run the solvers")
    check.add_argument("--deck", metavar="FILE", help="registry deck to check against")
    check.set_defaults(run=cmd_check)

    explain_cmd = commands.add_parser("explain", help="print the elaborated statements")
    design_file(explain_cmd)
    explain_cmd.set_defaults(run=cmd_explain)

    env = commands.add_parser("envelope", help="find the widest proved interval of one input")
    design_file(env)
    env.add_argument("--input", required=True, metavar="NAME", help="an input's label stem (ambient, lighting.supply.fault_current, lamp_draw.lighting.lamps.current) or a param")
    env.add_argument("--from", dest="lo", required=True, metavar="QTY", help='the low end of the probe range, such as "-20 degC"')
    env.add_argument("--to", dest="hi", required=True, metavar="QTY", help="the high end of the probe range")
    env.add_argument("--at", metavar="QTY", help="the anchor the envelope grows from; default the middle of the stated range")
    env.add_argument("--resolution", metavar="QTY", help="stop when each undecided gap is at most this; default 1/64 of the probe range, never finer than 1/2^20 of it")
    env.add_argument("--max-probes", type=int, default=64, metavar="N", help="the most checks to run, at least 4; default 64")
    env.add_argument("--library", metavar="DIR", help="family library to reuse evidence from")
    env.add_argument("--json", action="store_true", help="print the envelope as JSON")
    env.set_defaults(run=cmd_envelope)

    verify = commands.add_parser("verify", help="kernel-check certificate files on their own")
    verify.add_argument("certs", nargs="+", metavar="CERT")
    verify.set_defaults(run=cmd_verify)

    family = commands.add_parser("certify-family", help="certify a family design into a library")
    design_file(family)
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
    recall_cmd = decks.add_parser("recall", help="print the designs whose verdicts rest on a registry entry")
    recall_cmd.add_argument("id", metavar="ID", help="a registry entry, premise key, common name or id prefix")
    recall_cmd.add_argument("files", nargs="*", metavar="FILE",
                            help=".petra designs, saved `petra check --json` reports or directories; default examples/")
    recall_cmd.add_argument("--json", action="store_true", help="print the recall as JSON")
    recall_cmd.set_defaults(run=cmd_registry_recall)

    _add_teach_commands(commands, decks)
    _mcp_arguments(commands.add_parser(
        "mcp", help="serve check, kinds, new, registry_list and docs to an MCP client over stdio",
        description="Run an MCP server on stdin and stdout, for a coding agent's client to "
                    "start. `petra docs skill` shows how to add it to a client."))
    return parser


def _seconds(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError("the budget is more than 0 seconds")
    return value


def _mcp_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """What `petra mcp` takes. main() parses these on their own parser, because
    build_parser imports every model for its help and a client waits for the handshake."""
    from .mcp import BUDGET_S

    parser.add_argument("--budget", type=_seconds, default=BUDGET_S, metavar="SECONDS",
                        help="stop a tool call that runs longer than this (default %(default)g)")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(run=cmd_mcp)
    return parser


def _input_error(exc: BaseException) -> int:
    print(f"petra: {exc}", file=sys.stderr)
    return EXIT_CODES["INPUT_ERROR"]


def cmd_check(args: argparse.Namespace) -> int:
    """repair.check_text on the file, print its text() or json.dumps(to_json(),
    sort_keys=True). Returns EXIT_CODES[status], or EXIT_CODES["INPUT_ERROR"] when the file
    or the deck cannot be read or the design does not lower (message on stderr)."""
    from .certs import CertStore
    from .files import read_pair
    from .library import Library
    from .registry import build_registry, read_deck
    from .repair import check_text
    from .solvers import SolverSource

    try:
        registry = build_registry()
        card, text = read_pair(args.file, args.card)
        deck = read_deck(args.deck) if args.deck else None
        store = CertStore(args.certs) if args.certs else None
        library = Library(args.library) if args.library else None
    except _input_errors() as exc:
        return _input_error(exc)
    sources = tuple(s for s in (store, library, None if args.no_solve else SolverSource()) if s is not None)
    checked = check_text(card, text, args.file, registry, sources, sink=store, deck=deck, moves=not args.no_solve, card_path=args.card)
    if checked.report is None:
        return _input_error(checked.error)
    print(json.dumps(checked.to_json(), sort_keys=True) if args.json else checked.text())
    return EXIT_CODES[checked.status]


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp import main as serve

    return serve(args.budget, args.worker)


def cmd_explain(args: argparse.Namespace) -> int:
    from .lang import load_design
    from .pipeline import explain
    from .registry import build_registry

    try:
        registry = build_registry()
        text = explain(load_design(args.file, registry, args.card), registry)
    except _input_errors() as exc:
        return _input_error(exc)
    print(text)
    return 0


def cmd_envelope(args: argparse.Namespace) -> int:
    from .envelope import EnvelopeError, envelope, render, to_json
    from .lang import load_design
    from .library import Library
    from .registry import build_registry
    from .solvers import SolverSource
    from .units import UnitError
    from .verdict import SEVERITY

    try:
        registry = build_registry()
        design = load_design(args.file, registry, args.card)
        quantities = [None if text is None else _quantity(text) for text in (args.lo, args.hi, args.at, args.resolution)]
        written = (_QUANTITY.fullmatch(text).group(2) for text in (args.lo, args.hi, args.at) if text is not None)
        unit = next((u for u in written if u), None)
        library = Library(args.library) if args.library else None
        sources = tuple(s for s in (library, SolverSource()) if s is not None)
        found = envelope(design, registry, args.input, quantities[0], quantities[1], sources, at=quantities[2], resolution=quantities[3],
                         max_probes=args.max_probes, unit=unit)
    except (*_input_errors(), EnvelopeError, UnitError) as exc:
        return _input_error(exc)
    print(json.dumps(to_json(found), sort_keys=True) if args.json else render(found))
    if found.start.status not in SEVERITY:
        return EXIT_CODES["INPUT_ERROR"]
    statuses = [found.start.status, *([found.elsewhere] if found.elsewhere in SEVERITY else [])]
    return EXIT_CODES[max(statuses, key=SEVERITY.__getitem__)]


_QUANTITY = re.compile(r"\s*([+-]?[0-9]+(?:\.[0-9]+|/[0-9]+)?)\s*(\S*)\s*")


def _quantity(text: str) -> Quantity:
    """ "-20 degC", "-20degC", "1/2" or "30 %" as an exact quantity."""
    from .units import UnitError, parse_quantity

    match = _QUANTITY.fullmatch(text)
    if match is None:
        raise UnitError(f"{text!r} is not a number with an optional unit")
    number, unit = match.groups()
    return parse_quantity(number, unit or None)


def cmd_verify(args: argparse.Namespace) -> int:
    """The statement comes from the file, so a pass says only that the evidence proves
    the statement written there; `petra check` is what ties a statement to a design."""
    from . import kernel
    from .certs import CertificateError

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
    from .certs import CertificateError, decode_certificate

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
    from .lang import load_design
    from .library import Library, certify_family
    from .registry import build_registry
    from .verdict import Refuted

    try:
        registry = build_registry()
        design = load_design(args.file, registry, args.card)
        result = certify_family(design, registry, Library(args.library))
    except (*_input_errors(), ValueError) as exc:
        return _input_error(exc)
    for entry in result.stored:
        print(f"stored   {entry.family_key} (shape {entry.shape_hash})")
    for reason in result.near:
        print(f"margin   {reason}")
    for reason in result.skipped:
        print(f"skipped  {reason}")
    if not result.skipped:
        return EXIT_CODES["MARGINAL"] if result.near else EXIT_CODES["PASS"]
    if any(isinstance(o, Refuted) for o in result.report.outcomes):
        return EXIT_CODES["FAIL"]
    return EXIT_CODES["UNKNOWN"]


def cmd_registry_build(args: argparse.Namespace) -> int:
    from .registry import build_deck, write_deck

    try:
        write_deck(build_deck(), args.out)
    except OSError as exc:
        return _input_error(exc)
    print(f"wrote {args.out}")
    return 0


def cmd_registry_check(args: argparse.Namespace) -> int:
    """registry.check_deck on the given deck, or on registry.build_deck() when none is
    given. Prints each flagged relation."""
    from .registry import DeckError, build_deck, check_deck, read_deck

    try:
        deck = read_deck(args.deck) if args.deck else build_deck()
    except (DeckError, OSError) as exc:
        return _input_error(exc)
    findings = check_deck(deck)
    for f in findings:
        print(f"{f.entry}: {f.relation}: {f.message} (lhs {f.lhs.lo}..{f.lhs.hi}, rhs {f.rhs.lo}..{f.rhs.hi})")
    print(f"{len(deck.records)} records, {len(findings)} findings")
    return 1 if findings else 0


def cmd_registry_recall(args: argparse.Namespace) -> int:
    from .recall import RecallError, recall, render, to_json
    from .registry import build_registry

    try:
        found = recall(build_registry(), args.id, args.files)
    except RecallError as exc:
        return _input_error(exc)
    print(json.dumps(to_json(found), sort_keys=True) if args.json else render(found))
    return EXIT_CODES["INPUT_ERROR"] if found.errors else 0


# --- Teaching: kinds, new, registry list (petra/teach.py) --------------------------------


def _add_teach_commands(commands: argparse._SubParsersAction, decks: argparse._SubParsersAction) -> None:
    from . import models
    from .teach import DOCS

    kinds = commands.add_parser("kinds", help="print the component kinds and the lines each takes",
                                description="With no argument, print each domain and its component kinds. With a "
                                            "DOMAIN or a KIND, print the load and claim forms of each kind it names "
                                            "and its attribute lines, with their units, registry ids and meanings.")
    kinds.add_argument("name", nargs="?", metavar="DOMAIN|KIND",
                       help=f"a domain ({', '.join(models.DOMAINS)}) or a component kind ({', '.join(models.KINDS)})")
    kinds.add_argument("--all", action="store_true", help="print the lines of every kind")
    kinds.add_argument("--json", action="store_true", help="print the kinds as JSON: every kind unless DOMAIN|KIND is given")
    kinds.set_defaults(run=cmd_kinds)
    new = commands.add_parser("new", help="print a complete design of one kind, or its card, to start from",
                              description="Print a complete design of KIND, its canonical example, to edit, or with "
                                          "--card the card that design answers. `petra kinds KIND` lists every line "
                                          "a KIND takes.")
    new.add_argument("kind", metavar="KIND", help=f"the component kind: {', '.join(models.KINDS)}")
    new.add_argument("--name", metavar="NAME", help="the component's name; default the example's")
    new.add_argument("--card", action="store_true", help="print the card in place of the design")
    new.set_defaults(run=cmd_new)
    docs = commands.add_parser("docs", help="print the README, the language reference or the API",
                               description="Print a document that comes with Petra, or list them.")
    docs.add_argument("name", nargs="?", metavar="NAME",
                      help=f"the document: {', '.join(DOCS)}; leave it out to list them with what each covers")
    docs.set_defaults(run=cmd_docs)
    listing = decks.add_parser("list", help="print the registry ids a design can name")
    listing.add_argument("prefix", nargs="?", metavar="PREFIX")
    listing.set_defaults(run=cmd_registry_list)


def cmd_kinds(args: argparse.Namespace) -> int:
    from .teach import TeachError, kinds_json, kinds_summary, kinds_text

    try:
        if args.all and args.name is not None:
            raise TeachError(f"--all prints every kind; give it or {args.name}, not both")
        if args.json:
            text = json.dumps(kinds_json(args.name), indent=1) + "\n"
        else:
            text = kinds_text(args.name) if args.all or args.name is not None else kinds_summary()
    except TeachError as exc:
        return _input_error(exc)
    print(text, end="")
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    from .teach import TeachError, docs_text

    try:
        text = docs_text(args.name)
    except TeachError as exc:
        return _input_error(exc)
    print(text, end="")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    from .registry import build_registry
    from .teach import TeachError, new_text

    try:
        card, design = new_text(args.kind, args.name, build_registry())
    except (*_input_errors(), TeachError) as exc:
        return _input_error(exc)
    print(card if args.card else design, end="")
    return 0


def cmd_registry_list(args: argparse.Namespace) -> int:
    from .registry import build_registry
    from .teach import TeachError, registry_text

    try:
        registry = build_registry()
        print(registry_text(registry, args.prefix, registry.constants), end="")
    except TeachError as exc:
        return _input_error(exc)
    return 0


_QUANTITY_FLAGS = ("--from", "--to", "--at", "--resolution")


def _join_negative(argv: list[str]) -> list[str]:
    """["--from", "-20degC"] -> ["--from=-20degC"]: argparse takes a value that starts
    with "-" and is not a plain number for an option, so a negative quantity with its
    unit attached would be refused."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] in _QUANTITY_FLAGS and i + 1 < len(argv) and _QUANTITY.fullmatch(argv[i + 1]) and argv[i + 1].lstrip().startswith("-"):
            out.append(f"{argv[i]}={argv[i + 1]}")
            i += 2
        else:
            out.append(argv[i])
            i += 1
    return out


def main(argv: list[str] | None = None) -> int:
    try:
        argv = _join_negative(sys.argv[1:] if argv is None else list(argv))
        mcp = argv[:1] == ["mcp"]
        args = _mcp_arguments(_Parser(prog="petra mcp")).parse_args(argv[1:]) if mcp else build_parser().parse_args(argv)
        code = args.run(args)
        sys.stdout.flush()
        return code
    except Exception as exc:  # an uncaught crash would exit 1, which reads as FAIL
        if _reader_closed(exc):
            # Point stdout at the null device, or the flush at exit raises again.
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
            return EXIT_CODES["BROKEN_PIPE"]
        traceback.print_exc()
        return EXIT_CODES["INTERNAL_ERROR"]


def _reader_closed(exc: Exception) -> bool:
    """Whether `exc` is a write to stdout failing because its reader closed the pipe, as
    `petra check FILE | head` does: EPIPE, or on Windows EINVAL when the reader went before
    the write began."""
    if isinstance(exc, BrokenPipeError):
        return True
    if os.name != "nt" or not isinstance(exc, OSError) or exc.errno != errno.EINVAL:
        return False
    try:
        return stat.S_ISFIFO(os.fstat(sys.stdout.fileno()).st_mode)
    except (OSError, ValueError):
        return False
