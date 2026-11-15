"""Command line. Untrusted shell: parses arguments, calls the pipeline, prints.

    python -m petra check FILE [--card CARD] [--json]
        FILE is a design and CARD the card it answers, the .card file beside FILE when
        --card is left out. Parse the pair, hand its files to petra-verify with the deck
        of rules whose types its parts are, and print the kernel's verdict with every cell
        of the deck's grid (petra/pipeline.py). The `card` and `design` lines give the
        SHA-256 of each text, and `rules` the hash of the deck. The status on the first
        line is the verdict of petra-verify (petra/verify.py). A design none of whose parts
        is of a deck's type reads UNKNOWN, with a `reason` line that says which kinds no deck
        has: the kernel is not asked about it. One that mixes such parts with a deck's is an
        input error.
        --json prints the same as data (`petra docs api`).
        Exit code from the status, which is the kernel's own: 0 PASS, 1 FAIL, 2 UNKNOWN,
        and 6 PASS_WAIVED where the kernel says PASS and lists a waiver that a cell
        rests on (the JSON lists each such waiver under "waived"). 3 input error
        (syntax, lowering, a part its deck's types refuse, or a pair the kernel finds
        ill formed; nothing is printed to stdout). 4 no verdict of a design of a deck:
        there is no kernel to run, or its exit code or its error stream is at odds with what it printed, or
        its cells are not the ones the Python reader worked out. Nothing is printed to
        stdout, and nothing else gives a verdict.
    python -m petra kinds [DECK|TYPE] [--all] [--json]
        With no argument, print each shipped deck of rules and its types. With DECK or
        TYPE, or with --all for every type, print what a design writes for a part of each
        type, what a card may put on it, and what the grid asks of it, each mechanism with
        its rule or as open (petra/teach.py). --json prints every type unless DECK or TYPE
        names some. 3 for an unknown name, or a name with --all.
    python -m petra new TYPE [--name NAME] [--card]
        Print a complete design of TYPE to start from, its canonical example with the
        part renamed to NAME, or with --card the card it answers, which signs no waiver.
        3 for an unknown type or a name the design cannot take.
    python -m petra docs [NAME]
        Print the document NAME: readme, reference (the language), api (the Python API
        and the JSON) or skill (a SKILL.md for coding agents). With no NAME, list them.
        3 for an unknown name.
    python -m petra mcp [--budget SECONDS]
        Serve check, kinds, new and docs to an MCP client, JSON-RPC over stdin and
        stdout, until stdin closes (petra/mcp.py). A tool call that runs longer than the
        budget is stopped and says so. Exit 0. A client starts the server as `petra mcp`,
        the installed command, and not as `python -m petra mcp`: with -m, Python looks in
        the working directory first, and a workspace that holds a file named petra.py or
        a folder named petra would be run in Petra's place.
    python -m petra --version
        Print the version.

A usage error (an unknown subcommand or flag) is an input error too and exits 3. A crash
(a bug) prints its traceback and exits 4, so it never reads as a verdict. When the reader
closes stdout early, as `petra check FILE | head` does, the subcommand stops writing and
exits 141 without a traceback.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import stat
import sys
import traceback
from typing import Mapping, NoReturn

EXIT_CODES: Mapping[str, int] = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "INPUT_ERROR": 3, "INTERNAL_ERROR": 4, "PASS_WAIVED": 6, "BROKEN_PIPE": 141}
"""`petra check` exits with the code of the kernel's verdict: PASS, FAIL and UNKNOWN are
the kernel's own 0, 1 and 2, and INPUT_ERROR is its 3 for an ill-formed pair. INTERNAL_ERROR
is also what it exits with when there is no verdict (verify.NoVerdict). PASS_WAIVED: the
kernel says PASS, and a cell rests on a waiver (grid.PASS_WAIVED). No command exits 5, which
was the code of a status the Python checker had. BROKEN_PIPE: the reader closed stdout
before Petra finished writing. 141 is 128 plus SIGPIPE's number, the status a shell reports
for a command that a closed pipe stopped."""


def _input_errors() -> tuple[type[Exception], ...]:
    """The exceptions that are input errors. A command imports what it uses when it runs,
    so that `petra mcp` starts without the language or the grid."""
    from .pipeline import INPUT_ERRORS

    return (*INPUT_ERRORS, OSError)


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, which `petra check` reserves for UNKNOWN."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_CODES["INPUT_ERROR"], f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """Subcommands check, kinds, new, docs and mcp, with the flags in the module docstring."""
    from . import __version__

    parser = _Parser(prog="petra", description="check a physical design against a deck of rules, with the verdict of a small kernel",
                     formatter_class=argparse.RawDescriptionHelpFormatter,
                     epilog="Coding agents: `petra docs skill` prints a SKILL.md on designing and checking with Petra,\n"
                            "and `petra mcp` serves Petra's tools to an MCP client over stdio.\n"
                            "The README, the language reference, the Python API and that skill come with Petra:\n"
                            "`petra docs` lists them, and `petra docs NAME` prints one.")
    parser.add_argument("--version", action="version", version=f"petra {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    check = commands.add_parser("check", help="check a design against its card and print the kernel's verdict")
    check.add_argument("file", help="the design, a .petra file")
    check.add_argument("--card", metavar="FILE", help="the card the design answers; default the .card file beside the design")
    check.add_argument("--json", action="store_true", help="print the report as JSON")
    check.set_defaults(run=cmd_check)

    _add_teach_commands(commands)
    _mcp_arguments(commands.add_parser(
        "mcp", help="serve check, kinds, new and docs to an MCP client over stdio",
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
    build_parser reads the decks for its help and a client waits for the handshake."""
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
    """pipeline.check_text on the file, print its text() or json.dumps(to_json(),
    sort_keys=True). Returns EXIT_CODES[status], where the status is the kernel's verdict,
    or EXIT_CODES["INPUT_ERROR"] when a file cannot be read or the pair is refused (message
    on stderr). With no kernel to run, or one whose answer cannot be taken, there is no
    verdict: nothing goes to stdout, the reason goes to stderr, and the code is
    EXIT_CODES["INTERNAL_ERROR"]."""
    from . import verify
    from .files import read_pair
    from .pipeline import check_text

    try:
        card, text = read_pair(args.file, args.card)
    except _input_errors() as exc:
        return _input_error(exc)
    try:
        checked = check_text(card, text, args.file, card_path=args.card)
    except verify.Disagreement:
        raise      # a bug in the kernel or in the Python reader: a crash, with its traceback
    except verify.NoVerdict as exc:
        print(f"petra: no verdict: {exc}", file=sys.stderr)
        return EXIT_CODES["INTERNAL_ERROR"]
    if checked.error is not None:
        return _input_error(checked.error)
    print(json.dumps(checked.to_json(), sort_keys=True) if args.json else checked.text())
    return EXIT_CODES[checked.status]


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp import main as serve

    return serve(args.budget, args.worker)


# --- Teaching: kinds, new, docs (petra/teach.py) ------------------------------------------


def _add_teach_commands(commands: argparse._SubParsersAction) -> None:
    from . import grid
    from .teach import CANONICAL, DOCS

    kinds = commands.add_parser("kinds", help="print the decks of rules, their types of part and the lines each takes",
                                description="With no argument, print each deck of rules and its types. With a DECK or "
                                            "a TYPE, print what a design writes for a part of each type it names, the "
                                            "loads a card may put on it, and what the grid asks of it.")
    kinds.add_argument("name", nargs="?", metavar="DECK|TYPE",
                       help=f"a deck ({', '.join(d.name for d in grid.decks())}) or a type ({', '.join(grid.kinds())})")
    kinds.add_argument("--all", action="store_true", help="print the lines of every type")
    kinds.add_argument("--json", action="store_true", help="print the types as JSON: every type unless DECK|TYPE is given")
    kinds.set_defaults(run=cmd_kinds)
    new = commands.add_parser("new", help="print a complete design of one type, or its card, to start from",
                              description="Print a complete design of TYPE, its canonical example, to edit, or with "
                                          "--card the card that design answers. `petra kinds TYPE` lists every line "
                                          "a TYPE takes.")
    new.add_argument("kind", metavar="TYPE", help=f"the type of part: {', '.join(CANONICAL)}")
    new.add_argument("--name", metavar="NAME", help="the part's name; default the example's")
    new.add_argument("--card", action="store_true", help="print the card in place of the design")
    new.set_defaults(run=cmd_new)
    docs = commands.add_parser("docs", help="print the README, the language reference or the API",
                               description="Print a document that comes with Petra, or list them.")
    docs.add_argument("name", nargs="?", metavar="NAME",
                      help=f"the document: {', '.join(DOCS)}; leave it out to list them with what each covers")
    docs.set_defaults(run=cmd_docs)


def cmd_kinds(args: argparse.Namespace) -> int:
    from .teach import TeachError, kinds_json, kinds_summary, kinds_text

    try:
        if args.all and args.name is not None:
            raise TeachError(f"--all prints every type; give it or {args.name}, not both")
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
    from .teach import TeachError, new_text

    try:
        card, design = new_text(args.kind, args.name)
    except (*_input_errors(), TeachError) as exc:
        return _input_error(exc)
    print(card if args.card else design, end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Every command but the server prints through petra.files.guarded: nothing that a card, a design, a deck or the name of a
    file holds reaches a terminal as a character it acts on, and an argument that holds one is refused."""
    from .files import guarded

    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["mcp"]:        # the server writes bytes of its own to the stream, and its texts are JSON
        return _main(argv)
    return guarded(_main, argv)


def _main(argv: list[str]) -> int:
    try:
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
