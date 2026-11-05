"""Command line. Untrusted shell: parses arguments, builds evidence sources, prints.

    python -m lola check FILE [--json] [--certs DIR] [--library DIR] [--no-solve] [--deck FILE]
        Elaborate, gather evidence (certs, then library, then solvers unless --no-solve),
        kernel-check, print one verdict per claim plus the "coverage" entry, with each
        footprint. --json prints pipeline.Report.to_json():
            {"file": FILE, "design": NAME, "status": OVERALL, "verdicts": [
                {"claim": NAME, "status": "PASS" | "FAIL" | "UNKNOWN",
                 "footprint": [{"tag", "label", "owner", "source"}, ...],
                 "rules": ["R1", ...],
                 "obligations": [what each open item needs, ...]},   non-empty iff UNKNOWN
                ...]}
        Exit code from the overall status (EXIT_CODES): 0 PASS, 1 FAIL, 2 UNKNOWN,
        3 input error (syntax, lowering or ComponentError; nothing is printed to stdout).
    python -m lola explain FILE
        Print the elaborated statements with hypothesis labels.
    python -m lola verify CERT.json [...]
        Kernel-check certificate files on their own (statement taken from the file).
        This is what a Lean kernel will reimplement.
    python -m lola certify-family FILE --library DIR
    python -m lola registry build --out DECK.json
    python -m lola registry check [DECK.json]
        Run the deck consistency checker. With no DECK, check the deck built from the
        shipped registry. Exit 0 when every relation holds, 1 when one fails, 3 when the
        deck does not parse.
    python -m lola gym --episodes N --seed S [--domain NAME ...] [--library DIR]
        Run the baseline agent. Prints one summary line, AgentStats.render():
        "solved k/N episodes (library hits h, families added f)". --domain takes names
        from lola.models.DOMAINS that gym.tasks.GENERATORS covers; default all of them.

The family benchmark is scripts/bench_family.py, not a subcommand.
"""
from __future__ import annotations

import argparse
from typing import Mapping

EXIT_CODES: Mapping[str, int] = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "INPUT_ERROR": 3}


def build_parser() -> argparse.ArgumentParser:
    """Subcommands check, explain, verify, certify-family, registry (build, check) and
    gym, with the flags in the module docstring."""
    raise NotImplementedError


def cmd_check(args: argparse.Namespace) -> int:
    """Load, check_design, print render() or json.dumps(to_json(), sort_keys=True).
    Returns EXIT_CODES[report status], or EXIT_CODES["INPUT_ERROR"] on LolaSyntaxError,
    LoweringError or ComponentError (message on stderr)."""
    raise NotImplementedError


def cmd_registry_check(args: argparse.Namespace) -> int:
    """registry.check_deck on the given deck, or on registry.build_deck() when none is
    given. Prints each flagged relation."""
    raise NotImplementedError


def cmd_gym(args: argparse.Namespace) -> int:
    """gym.run_episodes(domains, args.episodes, args.seed, args.library) and print
    stats.render(). Returns 0 when it ran, whatever the solve rate."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError
