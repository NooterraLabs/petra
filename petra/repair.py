"""Which input to change on a FAIL, and which way. Untrusted tooling: it reads reports and
never changes a verdict.

A FAIL's governing check is its refuted obligation that ranks first the way the readout
ranks terms: a rule that is not met, then the highest utilisation. `repair` edits each
number written on a component's line (a Site) one step up and one step down, checks each
edited design, and keeps the moves that lower that check's utilisation. The moves come
sorted, so the first lowers it most. For the first three, it also searches outward for a
value at which the check holds, doubling the step and then halving it, and reports the
design's status there.

A step is the smallest edit the design accepts. Inches step by 1/16 in, a count by 1, and
any other number by a tenth of its leading digit's place, so 30 m steps by 1 m and 2.5 mm2
by 0.1 mm2. An edit that the language or the domain refuses (a plate thickness the shop
deck does not stock, a bolt diameter that RCSC Table 5.2 does not list) is not a step,
and the search walks on to the next number.

When no number lowers the check, `repair` swaps instead: each angle or tee the connection
adds for every other shape of its family in the shapes table, keeping the swaps that lower
the check, the ones that leave the fewest failed checks first.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable, Iterator, Mapping

from . import export, models, verify, wellformed
from .files import card_of
from .lang import LolaSyntaxError, LoweringError, parse_design
from .lang.lexer import Kind, tokenize
from .lang.parser import NOT_UNITS
from .models.base import ComponentError
from .pipeline import Report, check_design
from .readout import Finding
from .verdict import SEVERITY, STATUS

INPUT_ERRORS = (LolaSyntaxError, LoweringError, ComponentError)
"""What a design that does not lower raises: the edit is not a step."""

INCH_STEP = Fraction(1, 16)
LADDER = 64
"""The most steps a search takes in one direction from the written value."""
CLEARED = 3
"""How many of the best moves get a search for the value at which the check holds."""
SHAPE_PARTS = ("angles", "angle", "top_angle", "tee")
"""The lines that name a rolled shape the connection adds, which a swap move changes."""


@dataclass(frozen=True)
class Site:
    """A number written on a component's attribute line: one input a move edits. `input` names it as `<component>.<key>`, with the word before the number
    when that word is not the key, as in `tab.plate thickness`. A shape site (shape_sites)
    holds the shape named on an angle or tee line instead, and has no value."""

    input: str
    line: int
    col: int
    text: str
    unit: str | None

    def value(self) -> Fraction:
        return Fraction(self.text)


def sites(text: str) -> tuple[Site, ...]:
    """Every number on a component's lines of a design, in the order written. A number in
    a tuple is not a site: the tuples are coordinates the design is drawn on. Nothing in
    the card is a site: a repair changes the design and never what was asked of it."""
    return tuple(site for component, line in _component_lines(text) for site in _line_sites(component, line))


def shape_sites(text: str, registry: Any) -> tuple[Site, ...]:
    """The shape on each of a component's SHAPE_PARTS lines, written as a registry id that
    has a family to swap within (see `family`)."""
    return tuple(Site(f"{component}.{line[0].text}", line[1].line, line[1].col, line[1].text, None)
                 for component, line in _component_lines(text)
                 if line[0].text in SHAPE_PARTS and len(line) > 1 and line[1].kind is Kind.IDENT
                 and family(line[1].text, registry))


def family(shape: str, registry: Any) -> list[str]:
    """The other shapes of `shape`'s family in the shipped shapes table: every angle for an
    angle, every tee cut from one of its W shapes for a tee, and nothing for any other name."""
    from .teach import tee_of

    names = {k.split(".")[1] for k in registry.constants if k.startswith("aisc_shapes_v16.")}
    if shape.startswith("L") and shape in names:
        return sorted(n for n in names if n.startswith("L") and n != shape)
    tees = {t for n in names if n.startswith("W") and (t := tee_of(n))}
    return sorted(tees - {shape}) if shape in tees else []


def _component_lines(text: str) -> Iterator[tuple[str, list]]:
    """Each line inside a component block, as (the component's name, the line's tokens)."""
    lines: list[list] = [[]]
    for tok in tokenize(text, "<sites>"):
        if tok.kind is Kind.NEWLINE:
            lines.append([])
        elif tok.kind is not Kind.EOF:
            lines[-1].append(tok)
    component: str | None = None
    for line in lines:
        if not line:
            continue
        if component is None:
            if len(line) >= 3 and line[0].kind is Kind.IDENT and line[0].text in models.KINDS and line[2].text == "{":
                component = line[1].text
            continue
        if line[0].text == "}":
            component = None
            continue
        yield component, line


def _line_sites(component: str, line: list) -> list[Site]:
    key = line[0].text
    out = []
    depth = 0
    for i, tok in enumerate(line):
        if tok.kind is Kind.PUNCT and tok.text in "([":
            depth += 1
        elif tok.kind is Kind.PUNCT and tok.text in ")]":
            depth -= 1
        elif tok.kind is Kind.NUMBER and depth == 0 and i > 0:
            after = line[i + 1] if i + 1 < len(line) else None
            unit = after.text if after is not None and (after.kind is Kind.IDENT and after.text not in NOT_UNITS or after.text == "%") else None
            word = line[i - 1].text if line[i - 1].kind is Kind.IDENT and i > 1 else None
            out.append(Site(f"{component}.{key}" + (f" {word}" if word else ""), tok.line, tok.col, tok.text, unit))
    return out


def quantum(site: Site) -> Fraction:
    """One step of the site's number, in its written unit."""
    x = site.value()
    if site.unit in ("inch", "in"):
        return INCH_STEP
    if site.unit is None and x.denominator == 1:
        return Fraction(1)
    if x == 0:
        return Fraction(1)
    place = Fraction(1)
    while place > abs(x):
        place /= 10
    while place * 10 <= abs(x):
        place *= 10
    return place / 10


def written(x: Fraction, like: str) -> str:
    """`x` written the way `like` writes its number: p/q, a whole number or a decimal."""
    if "/" in like:
        return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"
    if x.denominator == 1 and "." not in like:
        return str(x.numerator)
    for places in range(1, 24):
        scaled = x * 10 ** places
        if scaled.denominator == 1:
            digits = str(abs(scaled.numerator)).rjust(places + 1, "0")
            whole, fraction = digits[:-places], digits[-places:].rstrip("0")
            return ("-" if x < 0 else "") + whole + (f".{fraction}" if fraction else "")
    return f"{x.numerator}/{x.denominator}"


def edit(text: str, site: Site, number: str) -> str:
    """The design with the site's number (or shape) replaced, the rest of the text untouched."""
    lines = text.split("\n")
    row = lines[site.line - 1]
    at = site.col - 1
    if row[at:at + len(site.text)] != site.text:
        raise ValueError(f"line {site.line} column {site.col} does not hold {site.text!r}")
    lines[site.line - 1] = row[:at] + number + row[at + len(site.text):]
    return "\n".join(lines)


def ladder(site: Site, direction: int) -> Iterator[tuple[int, str]]:
    """(k, number) for the site's value moved k steps in `direction` (+1 or -1), k = 1 to
    LADDER. A positive value never steps to zero or below."""
    x, q = site.value(), quantum(site)
    for k in range(1, LADDER + 1):
        y = x + direction * k * q
        if x > 0 and y <= 0:
            return
        yield k, written(y, site.text)


Checker = Callable[[str], "Report | None"]
"""A design's text -> its report, or None when the design does not lower."""


def checker(card: str, registry: Any, sources: tuple, path: str, deck: Any = None) -> Checker:
    """check_design over edited designs against the one card, each checked once. No sink: a
    probe records nothing."""
    seen: dict[str, Report | None] = {}

    def run(text: str) -> Report | None:
        if text not in seen:
            try:
                report = check_design(parse_design(card, text, path, registry), registry, sources, deck=deck, path=path)
                report.findings
            except INPUT_ERRORS:
                report = None
            seen[text] = report
        return seen[text]
    return run


# --- Moves -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    """The design with one site's number set to `to`, read for the governing check:
    `utilisation` and `outcome` are that check's after the edit, `status` the design's, and
    `fails` the requirements refuted there."""

    to: str
    utilisation: float | None
    outcome: str | None
    status: str
    fails: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {"to": self.to, "utilisation": _finite(self.utilisation), "status": self.status, "fails": list(self.fails)}


@dataclass(frozen=True)
class Move:
    """One step of one site, `direction` "increase" or "decrease", that lowers the governing
    check's utilisation. `clears` is the first value found in that direction at which the
    check is certified, or None when the search found none or did not run. A "swap" move
    puts another shape on a shape site; its `clears` is its step when the check holds there."""

    site: Site
    direction: str
    step: Probe
    clears: Probe | None

    def to_json(self) -> dict[str, Any]:
        s = self.site
        return {"input": s.input, "line": s.line, "from": s.text, "unit": s.unit, "direction": self.direction,
                **self.step.to_json(), "clears": None if self.clears is None else self.clears.to_json()}

    def text(self) -> str:
        s = self.site
        unit = f" {s.unit}" if s.unit else ""
        out = f"{self.direction:<9} {s.input} (line {s.line}) from {s.text} to {self.step.to}{unit}: utilisation {_ratio(self.step.utilisation)}"
        if self.clears is not None:
            where = "the design passes" if self.clears.status == "PASS" else f"the design is {self.clears.status}" + (
                f" on {', '.join(_short(r) for r in self.clears.fails)}" if self.clears.fails else "")
            out += f"; it holds there, and {where}" if self.direction == "swap" else f"; it holds at {self.clears.to}{unit}, where {where}"
        return out


@dataclass(frozen=True)
class Repair:
    """A FAIL's governing check (`check`, its requirement id, at `utilisation`) and the
    moves that lower it, best first."""

    check: str
    utilisation: float | None
    moves: tuple[Move, ...]

    def to_json(self) -> dict[str, Any]:
        return {"check": self.check, "utilisation": _finite(self.utilisation), "moves": [m.to_json() for m in self.moves]}

    def lines(self, shown: int = 3) -> list[str]:
        """The text `petra check` prints after the governing lines."""
        head = f"repair     {_short(self.check)} at utilisation {_ratio(self.utilisation)}"
        if not self.moves:
            return [f"{head}: no single number on a component's lines, and no other angle or tee, lowers it; "
                    "change a part or a grade"]
        rest = len(self.moves) - shown
        order = "the ones that leave the fewest failed checks first" if self.moves[0].direction == "swap" else "the first the most"
        return [f"{head}; each move lowers it, {order}:", *(f"  {m.text()}" for m in self.moves[:shown]),
                *([f"  {rest} more (--json lists each)"] if rest > 0 else [])]


def governing_failure(found: tuple[Finding, ...]) -> Finding | None:
    """The refuted finding that governs: a rule not met first, then the highest utilisation,
    then the first in report order."""
    refuted = [f for f in found if f.outcome == "refuted"]
    return max(refuted, key=_severity, default=None)


def repair(text: str, report: Report, check: Checker, registry: Any = None) -> Repair | None:
    """The moves for a FAIL report of `text`, or None when the report is not a FAIL. When
    no single number lowers the governing check and `registry` is given, the moves are the
    swaps of each angle or tee for another of its family that lower it."""
    if STATUS[type(report.verdict)] != "FAIL":
        return None
    target = governing_failure(report.findings)
    if target is None:
        return None
    before = _level(target)

    def lowers(probe: Probe) -> bool:
        after = _probe_level(probe)
        return after is not None and (before is None or after < before)

    moves: list[tuple[Move, int]] = []
    for site in sites(text):
        for direction in (1, -1):
            first = _first(text, site, direction, 1, check, target.requirement)
            if first is not None and lowers(first[1]):
                moves.append((Move(site, _WAY[direction], first[1], None), first[0]))
    if not moves and registry is not None:
        for site in shape_sites(text, registry):
            for shape in family(site.text, registry):
                report = check(edit(text, site, shape))
                probe = None if report is None else _read(shape, report, target.requirement)
                if probe is not None and lowers(probe):
                    moves.append((Move(site, "swap", probe, probe if probe.outcome == "certified" else None), 0))
    if moves and moves[0][0].direction == "swap":
        moves.sort(key=lambda mk: (SEVERITY[mk[0].step.status], len(mk[0].step.fails), _probe_level(mk[0].step)))
    else:
        moves.sort(key=lambda mk: (_probe_level(mk[0].step), SEVERITY[mk[0].step.status]))
    best = [_with_clears(text, m, k, check, target.requirement) if i < CLEARED and m.direction != "swap" else m
            for i, (m, k) in enumerate(moves)]
    return Repair(target.requirement, target.utilisation, tuple(best))


_WAY = {1: "increase", -1: "decrease"}


def _first(text: str, site: Site, direction: int, start: int, check: Checker, requirement: str) -> tuple[int, Probe] | None:
    """The first step at or past `start` that the design accepts, read for `requirement`."""
    for k, number in ladder(site, direction):
        if k < start:
            continue
        report = check(edit(text, site, number))
        if report is not None:
            return k, _read(number, report, requirement)
    return None


def _with_clears(text: str, move: Move, k: int, check: Checker, requirement: str) -> Move:
    """The move with the first value found at which the check is certified: double the step
    until it holds, then halve between the last step that failed and the first that held."""
    direction = 1 if move.direction == "increase" else -1
    if move.step.outcome == "certified":
        return Move(move.site, move.direction, move.step, move.step)
    low, held = k, None
    while held is None and low < LADDER:
        found = _first(text, move.site, direction, 2 * low, check, requirement)
        if found is None:
            return move
        if found[1].outcome == "certified":
            held = found
        else:
            low = found[0]
    if held is None:
        return move
    while held[0] - low > 1:
        found = _first(text, move.site, direction, (low + held[0]) // 2, check, requirement)
        if found is None or found[0] >= held[0]:
            break
        if found[1].outcome == "certified":
            held = found
        else:
            low = found[0]
    return Move(move.site, move.direction, move.step, held[1])


def _read(number: str, report: Report, requirement: str) -> Probe:
    found = report.findings
    mine = next((f for f in found if f.requirement == requirement), None)
    return Probe(number, None if mine is None else mine.utilisation, None if mine is None else mine.outcome,
                 STATUS[type(report.verdict)], tuple(f.requirement for f in found if f.outcome == "refuted"))


def _severity(f: Finding) -> tuple[bool, float]:
    g = f.governing
    return (g is not None and g.met is False, f.utilisation if f.utilisation is not None else 0.0)


def _level(f: Finding) -> float | None:
    """How far the check is from holding: its utilisation, 0 for a check now certified with
    none (a rule that is met), None when it was not read."""
    if f.utilisation is not None:
        return f.utilisation
    return 0.0 if f.outcome == "certified" else None


def _probe_level(p: Probe) -> float | None:
    if p.utilisation is not None:
        return p.utilisation
    return 0.0 if p.outcome == "certified" else None


def _short(requirement: str) -> str:
    """`tab/steel.bolts/coverage.steel.bolts` -> `tab/steel.bolts`."""
    return "/".join(requirement.split("/")[:2])


def _finite(x: float | None) -> float | None:
    return None if x is None or x != x or x in (float("inf"), float("-inf")) else x


def _ratio(x: float | None) -> str:
    return "unknown" if x is None else "unbounded" if x == float("inf") else f"{x:.3g}"


# --- One design checked from its text ------------------------------------------------------------


@dataclass(frozen=True)
class Checked:
    """A design checked from its text: its report and, on a FAIL, its repair; or, for a
    design that does not lower, the input error and no report. `card` names the card it
    was checked against, `hashes` holds the hash of the card's text and of the design's
    (export.sha256), and `kernel` is the kernel's word on the report, None when no kernel
    ran."""

    path: str
    report: Report | None
    repair: Repair | None
    error: str | None
    card: str = ""
    hashes: Mapping[str, str] | None = None
    kernel: verify.Kernel | None = None

    @property
    def status(self) -> str:
        return "INPUT_ERROR" if self.report is None else STATUS[type(self.report.verdict)]

    def to_json(self) -> dict[str, Any]:
        """The report's JSON with "card", "hashes", "kernel" and "repair", or
        {"file", "status": "INPUT_ERROR", "error"}."""
        if self.report is None:
            return {"file": self.path, "status": "INPUT_ERROR", "error": self.error}
        return {**self.report.to_json(), "card": self.card, "hashes": dict(self.hashes),
                "kernel": None if self.kernel is None else self.kernel.to_json(),
                "repair": None if self.repair is None else self.repair.to_json()}

    def text(self) -> str:
        """What `petra check` prints: the report, with what it was checked against and the
        kernel's word after its scope, and the repair after its governing lines."""
        if self.report is None:
            return f"{self.path}: INPUT_ERROR\n{self.error}"
        out = self.report.render().split("\n")
        at = max((i + 1 for i, line in enumerate(out[:8]) if line.startswith("governing  ")), default=min(2, len(out)))
        out = out[:at] + ([] if self.repair is None else self.repair.lines()) + out[at:]
        kernel = verify.NO_KERNEL if self.kernel is None else self.kernel.line(self.status)
        against = [f"card       {self.hashes['card']}  {self.card}", f"design     {self.hashes['design']}  {self.path}", f"kernel     {kernel}"]
        at = next((i + 1 for i, line in enumerate(out[:4]) if line.startswith("scope  ")), min(2, len(out)))
        return "\n".join(out[:at] + against + out[at:])


def check_text(card: str, text: str, path: str, registry: Any, sources: tuple, *, sink: Any = None, deck: Any = None,
               moves: bool = True, card_path: str | None = None) -> Checked:
    """Check the design `text` against the card and `registry` with `sources`, recording
    accepted evidence into `sink`, and have the kernel check the report when there is one
    to run (verify.py). `path` names the design in messages, and `card_path` the card
    when it is not the file beside it. With `moves`, a FAIL gets its repair, probed with
    the same card and sources, no sink and no kernel: a move is a suggestion."""
    try:
        design = parse_design(card, text, path, registry, card_path)
        wellformed.require(design, registry)
        proofs = export.Proofs(sink)
        report = check_design(design, registry, sources, sink=proofs, deck=deck, path=path)
        kernel = verify.verify(design, registry, report, proofs)
    except INPUT_ERRORS as exc:
        return Checked(path, None, None, str(exc))
    found = repair(text, report, checker(card, registry, sources, path, deck), registry) if moves else None
    hashes = {"card": export.sha256(card), "design": export.sha256(text)}
    return Checked(path, report, found, None, card_path or card_of(path), hashes, kernel)
