"""The three readers and what they say of one input.

A design checked against a deck of rules is read three times: by the kernel (`petra-verify`),
by the Python reader (`petra/grid.py`, which also writes the files the other two read) and by
the third reading (`bench/twin/verify.mjs`, written from the pages alone). `judge` runs all
three on a text pair and a deck, and `judge_files` runs the kernel and the third reading on
files that no language wrote. Each gives a `Judged`: what every reader said, and every way in
which they differ, as `Diff` items.

An input "reaches the comparison" when it is a pair the language reads and every reader is
asked. It is "settled" when the kernel then gives PASS, FAIL or UNKNOWN and not ILL-FORMED.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TWIN = ROOT / "bench" / "twin" / "verify.mjs"
SLOW = 90.0
"""Seconds a reader may take on one input. Past it the input is kept as a hang."""


@dataclass
class Diff:
    kind: str                # verdict, cells, reason, waived, findings, refusal, crash, hang, bundle, relation
    where: str               # what is compared: "kernel/twin", "kernel/grid", "grid", ...
    detail: str
    key: str = ""            # what two diffs share when they are one fault

    def sig(self) -> str:
        return hashlib.sha1(f"{self.kind}|{self.where}|{self.key}".encode()).hexdigest()[:10]


@dataclass
class Judged:
    reached: bool = False        # every reader was asked
    settled: bool = False        # the kernel gave PASS, FAIL or UNKNOWN
    outcome: str = ""            # why it did not reach, or the kernel's verdict
    verdict: dict[str, str] = field(default_factory=dict)       # reader -> verdict
    files: dict[str, str] = field(default_factory=dict)
    diffs: list[Diff] = field(default_factory=list)
    cells: list[tuple] = field(default_factory=list)            # the kernel's (subject, mechanism, entry, state, reason)
    seconds: float = 0.0


class Timeout(Exception):
    pass


@contextlib.contextmanager
def alarm(seconds: float):
    """Raise Timeout in this process after the time, on a platform that has SIGALRM. An alarm inside another keeps the outer one: it ends no later than the outer, and the outer runs on after it."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def fired(*_):
        raise Timeout()

    outer = signal.getitimer(signal.ITIMER_REAL)[0]
    began = time.monotonic()
    old = signal.signal(signal.SIGALRM, fired)
    signal.setitimer(signal.ITIMER_REAL, seconds if outer == 0 else min(seconds, outer))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
        if outer:
            signal.setitimer(signal.ITIMER_REAL, max(outer - (time.monotonic() - began), 0.001))


class Config:
    """Where the readers are. The defaults are this checkout's own; a run may name others."""
    kernel: str | None = os.environ.get("PETRA_VERIFY")
    twin: str = str(TWIN)
    node: str = "node"
    cli_share: int = 8       # one pair in this many also goes through `petra check`
    jobs_hint: int = 1


def _spawn(command: list[str]) -> subprocess.Popen:
    return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _collect(proc: subprocess.Popen, name: str) -> tuple[dict | None, Diff | None]:
    try:
        out, err = proc.communicate(timeout=SLOW)
    except BaseException as exc:       # the step's own alarm included: no reader is left running
        proc.kill()
        proc.communicate()
        if not isinstance(exc, subprocess.TimeoutExpired):
            raise
        return None, Diff("hang", name, f"{name} took over {SLOW:.0f} seconds", key=name)
    try:
        said = json.loads(out.decode("utf-8"))
        if not isinstance(said, dict) or "verdict" not in said:
            raise ValueError("no verdict")
        return said, None
    except ValueError:
        tail = (err or out).decode("utf-8", "replace")[-240:].strip()
        first = next((l for l in tail.splitlines() if l.strip()), "")
        return None, Diff("crash", name, f"{name} exited {proc.returncode} with no verdict: {tail}", key=f"{name}|{first[:60]}")


def ask_both(files: dict[str, str]) -> tuple[dict | None, dict | None, list[Diff]]:
    """The kernel's word and the third reading's on the files, started together."""
    with tempfile.TemporaryDirectory() as tmp:
        args: list[str] = []
        for name, body in files.items():
            p = Path(tmp, f"{name}.json")
            p.write_bytes(body.encode("utf-8", "surrogatepass") if isinstance(body, str) else body)
            args += [f"--{name}", str(p)]
        kernel = _spawn([Config.kernel or "petra-verify", *args])
        twin = _spawn([Config.node, Config.twin, *args])
        k, kd = _collect(kernel, "kernel")
        t, td = _collect(twin, "twin")
    return k, t, [d for d in (kd, td) if d]


def _cells(said: dict) -> list[tuple]:
    return [(c.get("subject"), c.get("mechanism"), c.get("entry"), c.get("state"), c.get("reason", "")) for c in said.get("cells", [])]


def _findings(said: dict) -> list[tuple]:
    return sorted({(f.get("file"), f.get("rule")) for f in said.get("findings", [])})


def compare_two(a: dict, b: dict, where: str, reasons: bool = True) -> list[Diff]:
    """How two readers' answers differ, the kernel's and the third reading's: verdict, then the cells, their reasons, the waivers and the findings."""
    out: list[Diff] = []
    if a["verdict"] != b["verdict"]:
        out.append(Diff("verdict", where, f"{a['verdict']} against {b['verdict']}", key=f"{a['verdict']}|{b['verdict']}|{_first_finding(a)}|{_first_finding(b)}"))
        return out
    if a["verdict"] == "ILL-FORMED":
        fa, fb = _findings(a), _findings(b)
        if fa != fb:
            out.append(Diff("findings", where, f"{fa[:4]} against {fb[:4]}", key=f"{[r for _, r in fa][:3]}|{[r for _, r in fb][:3]}"))
        return out
    ca, cb = _cells(a), _cells(b)
    if [c[:4] for c in ca] != [c[:4] for c in cb]:
        first = next((f"{x[:4]} against {y[:4]}" for x, y in zip(ca, cb) if x[:4] != y[:4]), f"{len(ca)} cells against {len(cb)}")
        mech = next((x[1] for x, y in zip(ca, cb) if x[:4] != y[:4]), "")
        out.append(Diff("cells", where, first, key=f"{mech}|{first.split('(')[0][:0]}{[(x[1], x[3]) for x, y in zip(ca, cb) if x[:4] != y[:4]][:2]}"))
    elif reasons:
        for x, y in zip(ca, cb):
            if x[3] in ("open", "waived", "refuted") and (x[4] != y[4] if x[3] == "refuted" else held(x[4]) != held(y[4])):
                out.append(Diff("reason", where, f"{x[0]}/{x[1]}/{x[2]} {x[3]}: {x[4]!r} against {y[4]!r}", key=f"{x[3]}|{_lead(x[4])}|{_lead(y[4])}"))
                break
        for x, y in zip(a.get("cells", []), b.get("cells", [])):
            if x.get("completion") != y.get("completion"):
                out.append(Diff("waived", where, f"{x.get('subject')}/{x.get('mechanism')}: completion {x.get('completion')} against {y.get('completion')}", key=f"completion|{x.get('mechanism')}"))
                break
    if a.get("waived") != b.get("waived") and not out:
        out.append(Diff("waived", where, f"{a.get('waived')} against {b.get('waived')}", key="waived-list"))
    return out


LEADS = ("open but for the waiver: ", "the waiver does not rest this cell: ")
NOT_PROVED = "the range the rule holds in is not proved: "


def held(reason: str) -> str:
    """What the pages hold of the reason of an open or a waived cell (format.md, The verdict): the start of the
    reason of a waived cell and of one a waiver does not rest, the start of the reason of a range that is not
    proved, and the whole reason of an unstated field, of a range that holds nowhere and of a cell that nothing
    reads. Every other reason is in the reader's own words, and so is the order of the loads a case leaves out:
    two readers that word those differently do not differ."""
    for lead in LEADS:
        if reason.startswith(lead):
            return lead + held(reason[len(lead):])
    if reason.startswith(NOT_PROVED):
        return NOT_PROVED
    given = (" is unstated: its maker states none, and " in reason or reason.startswith("the rule holds only where ")
             or (reason.startswith("no rule of the deck reads ") and reason.endswith(", so nothing checks it")))
    return reason if given else ""


def _shape(text: str) -> str:
    """A reason with its names and numbers taken out, so two reasons of one kind share a key."""
    import re
    return re.sub(r"[A-Za-z_][\w.]*\.[\w]+|\d+(?:/\d+)?|`[^`]*`", "#", text or "")[:60]


def _lead(text: str) -> str:
    """The first words of a reason, which say what kind it is."""
    import re
    return " ".join(re.sub(r"[A-Za-z_][\w.]*\.[\w]+|\d+(?:/\d+)?|`[^`]*`", "#", text or "").split()[:5])


def _first_finding(said: dict) -> str:
    f = said.get("findings") or []
    return str(f[0].get("rule")) if f else ""


# --- the language path

_DECKS: dict[str, Any] = {}


def read_deck(text: str):
    """grid.read_deck, remembered: a worker reads one deck for many designs. A refusal is remembered as the exception."""
    from petra import grid
    if text not in _DECKS:
        if len(_DECKS) > 24:
            _DECKS.pop(next(iter(_DECKS)))
        try:
            _DECKS[text] = grid.read_deck(text)
        except grid.DeckError as exc:
            _DECKS[text] = exc
    got = _DECKS[text]
    if isinstance(got, Exception):
        raise got
    return got


def judge(card: str, design: str, deck_text: str, base_text: str | None = None, cli: bool = False, extra: dict[str, str] | None = None) -> Judged:
    """All three readers on a pair of texts against a deck. `base_text` is the deck the language parses the design with when `deck_text` does not load."""
    from petra import grid, verify
    from petra.lang import parse_design
    from petra.models.base import ComponentError
    from petra.registry import build_registry
    from petra.repair import INPUT_ERRORS

    t0 = time.time()
    j = Judged()
    deck, refusal = None, ""
    try:
        with alarm(30):
            deck = read_deck(deck_text)
    except grid.DeckError as exc:
        refusal = str(exc)
    except Timeout:
        j.diffs.append(Diff("hang", "grid", "grid.read_deck took over 30 seconds", key="read_deck"))
    except Exception as exc:        # noqa: BLE001 a crash is a finding
        j.diffs.append(Diff("crash", "grid", f"grid.read_deck: {type(exc).__name__}: {exc}", key=f"read_deck|{type(exc).__name__}|{traceback.extract_tb(exc.__traceback__)[-1].lineno}"))
        refusal = f"crash {exc}"
    parse_with = deck
    if parse_with is None:
        try:
            parse_with = read_deck(base_text) if base_text else None
        except Exception:       # noqa: BLE001
            parse_with = None
    if parse_with is None:
        j.outcome = "no deck to read the design with"
        j.seconds = time.time() - t0
        return j
    registry = build_registry()
    with mock.patch.object(grid, "decks", lambda: (parse_with,)):
        try:
            with alarm(30):
                parsed = parse_design(card, design, "attack.petra", registry)
                if grid.owner(parsed) is None:
                    j.outcome = "no part of the deck's types"
                    j.seconds = time.time() - t0
                    return j
        except INPUT_ERRORS as exc:
            j.outcome = "the language refuses it: " + str(exc).replace("\n", " ")[:300]
            j.seconds = time.time() - t0
            return j
        except Timeout:
            j.diffs.append(Diff("hang", "language", "parse_design took over 30 seconds", key="parse_design"))
            return j
        except Exception as exc:        # noqa: BLE001
            j.diffs.append(Diff("crash", "language", f"parse_design: {type(exc).__name__}: {exc}", key=f"parse|{type(exc).__name__}|{traceback.extract_tb(exc.__traceback__)[-1].lineno}"))
            return j
        report, grid_refuses, files = None, "", {}
        try:
            with alarm(60):
                files = grid.bundle(parsed, parse_with)
                if deck is not None:
                    report, files = grid.check(parsed, deck)
        except (ComponentError, grid.DeckError) as exc:
            grid_refuses = str(exc)
            if deck is None:
                grid_refuses = refusal
        except Timeout:
            j.diffs.append(Diff("hang", "grid", "grid.check took over 60 seconds", key="check"))
            return j
        except Exception as exc:        # noqa: BLE001
            tb = traceback.extract_tb(exc.__traceback__)[-1]
            j.diffs.append(Diff("crash", "grid", f"grid.check: {type(exc).__name__}: {exc} ({Path(tb.filename).name}:{tb.lineno})", key=f"check|{type(exc).__name__}|{Path(tb.filename).name}:{tb.lineno}"))
            return j
        if deck is None:
            files = {**files, "rules": deck_text}
            grid_refuses = grid_refuses or refusal
        if extra:
            files = {**files, **extra}
    j.files = files
    j.reached = True
    kernel, twin, bad = ask_both(files)
    j.diffs += bad
    j.verdict = {"grid": "REFUSED" if report is None else report.verdict}
    if kernel:
        j.verdict["kernel"] = kernel["verdict"]
        j.settled = kernel["verdict"] != "ILL-FORMED"
        j.outcome = kernel["verdict"] + (": " + str((kernel.get("findings") or [{}])[0].get("rule")) + " " + str((kernel.get("findings") or [{}])[0].get("why", ""))[:100] if kernel["verdict"] == "ILL-FORMED" else "")
        j.cells = _cells(kernel)
    if twin:
        j.verdict["twin"] = twin["verdict"]
    if kernel and twin:
        j.diffs += compare_two(kernel, twin, "kernel/twin")
    if kernel:
        j.diffs += _against_grid(kernel, report, grid_refuses, deck, refusal)
    if cli and kernel and report is not None and not j.diffs:
        j.diffs += _through_cli(card, design, deck_text, deck, report)
    j.seconds = time.time() - t0
    return j


def _against_grid(kernel: dict, report: Any, refuses: str, deck: Any, deck_refusal: str) -> list[Diff]:
    """The kernel's answer against the grid's: both refuse, or both give the same verdict and the same cells."""
    out: list[Diff] = []
    ill = kernel["verdict"] == "ILL-FORMED"
    on_deck = any(f.get("file") == "rules" for f in kernel.get("findings", []))
    if report is None:
        if not ill:
            out.append(Diff("refusal", "kernel/grid", f"the grid refuses ({refuses[:160]}) and the kernel gives {kernel['verdict']}", key=f"grid-refuses|{_shape(refuses)[:40]}"))
        elif deck is None and not on_deck:
            out.append(Diff("refusal", "kernel/grid", f"the grid refuses the deck ({deck_refusal[:120]}) and the kernel the design: {_findings(kernel)[:2]}", key=f"deck-vs-design|{_shape(deck_refusal)[:40]}"))
        return out
    if ill:
        why = "; ".join(f"{f.get('item')}: {f.get('why')}" for f in kernel.get("findings", []))[:200]
        out.append(Diff("refusal", "kernel/grid", f"the kernel refuses ({why}) and the grid gives {report.verdict}", key=f"kernel-refuses|{_findings(kernel)[:2]}"))
        return out
    mine = [(c.subject, c.mechanism, c.entry, c.state) for c in report.cells]
    its = [(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in kernel["cells"]]
    if mine != its or report.verdict != kernel["verdict"]:
        first = next((f"grid {a}, kernel {b}" for a, b in zip(mine, its) if a != b), f"{len(mine)} cells against {len(its)}")
        kind = "verdict" if report.verdict != kernel["verdict"] else "cells"
        out.append(Diff(kind, "kernel/grid", f"{first}; verdicts {report.verdict} and {kernel['verdict']}",
                        key=f"{report.verdict}|{kernel['verdict']}|{[(a[1], a[3], b[3]) for a, b in zip(mine, its) if a != b][:2]}"))
        return out
    if report.waived() != kernel.get("waived") or report.completions() != [c.get("completion") for c in kernel["cells"]]:
        out.append(Diff("waived", "kernel/grid", f"waivers {report.waived()} against {kernel.get('waived')}", key="waived-list"))
    for c, k in zip(report.cells, kernel["cells"]):
        why = c.why or ""
        if c.state == "waived" and why.startswith("by ") and "; open but for the waiver: " in why:
            why = why[why.index("; open but for the waiver: ") + 2:]       # the grid names who signed, which the kernel prints elsewhere
        if c.state == "waived" and held(why) != held(k.get("reason", "")):      # the grid words its other reasons itself, and the pages say so
            out.append(Diff("reason", "kernel/grid", f"{c.subject}/{c.mechanism}/{c.entry} {c.state}: grid {why!r}, kernel {k.get('reason')!r}", key=f"{c.state}|{_lead(why)}|{_lead(k.get('reason', ''))}"))
            break
    if kernel["hashes"].get("rules") != deck.hash:
        out.append(Diff("cells", "kernel/grid", f"the kernel read the rules {kernel['hashes'].get('rules')} and the deck is {deck.hash}", key="rules-hash"))
    return out


def _through_cli(card: str, design: str, deck_text: str, deck: Any, report: Any) -> list[Diff]:
    """`petra check FILE --json` on the pair: it runs the kernel itself and exits 4 when the kernel and the grid differ."""
    import io
    from petra import grid
    from petra.cli import main
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "a.petra").write_text(design, encoding="utf-8", newline="\n")
        Path(tmp, "a.card").write_text(card, encoding="utf-8", newline="\n")
        out, err = io.StringIO(), io.StringIO()
        try:
            with mock.patch.object(grid, "decks", lambda: (deck,)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), alarm(120):
                code = main(["check", str(Path(tmp, "a.petra")), "--json"])
        except Timeout:
            return [Diff("hang", "cli", "petra check took over 120 seconds", key="cli")]
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        except Exception as exc:        # noqa: BLE001
            tb = traceback.extract_tb(exc.__traceback__)[-1]
            return [Diff("crash", "cli", f"petra check: {type(exc).__name__}: {exc} ({Path(tb.filename).name}:{tb.lineno})", key=f"cli|{type(exc).__name__}|{Path(tb.filename).name}:{tb.lineno}")]
    if code == 4:
        return [Diff("verdict", "cli", f"petra check exits 4: {(err.getvalue() or out.getvalue())[-300:].strip()}", key="cli-exit-4")]
    try:
        shown = json.loads(out.getvalue())
    except ValueError:
        return [Diff("crash", "cli", f"petra check --json printed no JSON (exit {code}): {out.getvalue()[-200:]!r} {err.getvalue()[-200:]!r}", key="cli-no-json")]
    status = shown.get("status") or shown.get("verdict")
    if status and report.verdict not in (status, ) and status != {"PASS": "PASS_WAIVED"}.get(report.verdict, "") and not (report.verdict == "PASS" and status == "PASS_WAIVED"):
        return [Diff("verdict", "cli", f"petra check says {status} and grid.check {report.verdict}", key=f"cli-status|{status}|{report.verdict}")]
    return []


# --- the file path

def judge_files(files: dict[str, str]) -> Judged:
    """The kernel and the third reading on files that no language wrote."""
    t0 = time.time()
    j = Judged(files=files, reached=True)
    kernel, twin, bad = ask_both(files)
    j.diffs += bad
    if kernel:
        j.verdict["kernel"] = kernel["verdict"]
        j.settled = kernel["verdict"] != "ILL-FORMED"
        j.outcome = kernel["verdict"]
        j.cells = _cells(kernel)
    if twin:
        j.verdict["twin"] = twin["verdict"]
    if kernel and twin:
        j.diffs += compare_two(kernel, twin, "kernel/twin")
    j.seconds = time.time() - t0
    return j


def bundle_of(card: str, design: str, deck_text: str) -> dict[str, str] | None:
    """The files the Python reader writes for a pair, with no kernel run, or None when the language or the grid refuses it."""
    from petra import grid
    from petra.lang import parse_design
    from petra.models.base import ComponentError
    from petra.registry import build_registry
    from petra.repair import INPUT_ERRORS
    try:
        deck = read_deck(deck_text)
        with mock.patch.object(grid, "decks", lambda: (deck,)):
            parsed = parse_design(card, design, "attack.petra", build_registry())
            if grid.owner(parsed) is None:
                return None
            try:
                with alarm(60):
                    return grid.check(parsed, deck)[1]
            except ComponentError:
                return grid.bundle(parsed, deck)
    except (*INPUT_ERRORS, grid.DeckError):
        return None
