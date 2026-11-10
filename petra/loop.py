"""The repair-and-minimise loop for steel connections (docs/plan.md P2). Untrusted
tooling: every verdict it acts on comes from the checker, and it changes none.

A Task is a job a user would give: a connection kind, the design basis, the members and
any line the job fixes (`beam`, `support`, a bracket's `eccentricity`), and the loads.
`tasks` draws them from the steel deck's design generator, so each comes with a design
the deck passes at that load (`reference`), which proves the job can be done.

`solve` runs the loop on one task:

1. Draft. Start from `petra new KIND` and write the task's lines and loads into it.
2. Repair. Check the design with petra.check. On a FAIL, take a move from its repair, as an
   agent reading the output would: a move whose `clears` value passes the design, else
   the clearing move that leaves the fewest failed checks, else the first move's step.
   Stop at PASS, or when `budget` checks are spent or no move leads to a new design.
   A move on a line the job fixes, such as a bracket's eccentricity, is never taken.
3. Minimise. From the PASS, push the mass of the connection's parts down while the
   design still passes: step each number on the component's lines toward less mass,
   doubling the step while it passes, and swap each angle or tee for a lighter one. A
   design is kept only when the checker returns PASS for it, so every margin the loop
   keeps is certified by the kernel, not estimated. MARGINAL is not kept.

`judge`, when given, reads every design the loop keeps (each PASS of the repair, each
step of the minimiser). A caller can pass the outside judge (judges/), which
computes the geometry independently, so the minimiser, which goes looking for the edge
of the passing region, is also a breaker.

`mass` estimates the steel the connection adds, in pounds: plates and stiffeners as
rectangles, angles and tees by their section over the connection's length, and each
bolt as its shank over a 2 in grip with a head and a nut. It ranks designs of one task
against each other. It is not a bill of materials.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable, Iterator

from .lang import parse_design
from .registry import Registry
from .registry.steel import INCH
from .repair import INPUT_ERRORS, Checked, Site, check_text, edit, family, ladder, shape_sites, sites
from .solvers import SolverSource
from .units import parse_quantity


TASK_KINDS = ("shear_tab", "double_angle", "single_angle", "shear_tee", "shear_end_plate", "seated", "stiffened_seat",
              "bolt_bracket", "weld_bracket", "hanger")
"""The steel kinds a task can be. flange_force checks a member under a flange force, with no
connection part to size, so it is not a design task."""

GIVEN = ("beam", "support", "eccentricity")
"""The lines a job fixes: the frame's members and where a bracket's load acts."""

SIGNER = "task.owner@example.org"
DENSITY = 490 / Fraction(1728)
"""Steel, lb per cubic inch."""


@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    basis: str
    given: tuple[str, ...]                   # attribute lines as written, "beam W18x35 grade steel.A992"
    loads: tuple[tuple[str, Fraction], ...]  # (field, the range's top in kip); each range starts at 0 kip
    reference: str

    def load_lines(self, component: str) -> list[str]:
        return [f"  on {component} {f} in [0 kip, {_kip(top)} kip]" for f, top in self.loads]

    def brief(self) -> str:
        """The job in words, as a user would give it."""
        members = "\n".join(f"- `{line}`" for line in self.given)
        loads = "\n".join(f"- {f}: from 0 to {_kip(top)} kip" for f, top in self.loads)
        return (f"Design a steel `{self.kind}` connection, {self.basis.upper()} (`basis {self.basis}`).\n\n"
                f"These lines are fixed by the job:\n\n{members}\n\n"
                f"Loads ({'factored' if self.basis == 'lrfd' else 'service'}), on the connection:\n\n{loads}\n\n"
                f'Sign the loads as "{SIGNER}" with source "task {self.id}".\n')

    def faithful(self, text: str, registry: Registry) -> list[str]:
        """What `text` changes of the job, empty when it keeps it: one component of the
        task's kind, its basis and given lines as the job states them (read through the
        deck's lowering, so A992 and steel.A992 agree), each load range reaching from 0 to
        at least the job's top, and no waiver."""
        from .models.steel import calc

        try:
            design = parse_design(text, "<faithful>", registry)
            mine = [c for c in design.components.values()]
            if len(mine) != 1 or mine[0].kind != self.kind:
                return [f"the design must hold one {self.kind}, not {', '.join(c.kind for c in mine) or 'nothing'}"]
            ours = calc.connection(design, mine[0].name, registry)
            job = parse_design(self.reference, "<reference>", registry)
            theirs = calc.connection(job, "c1", registry)
        except (*INPUT_ERRORS, KeyError) as exc:
            return [f"the design does not lower: {exc}"]
        out = [f"{key} differs from the job's" for key in ("basis", *GIVEN) if ours.get(key) != theirs.get(key)]
        if design.waivers:
            out.append("the design waives a requirement")
        kip = parse_quantity("1", "kip").value.lo
        entries = {e.field: e.value for case in design.loads.values() for e in case.entries}
        for f, top in self.loads:
            value = entries.get(f)
            rng = getattr(value, "range", None)
            if rng is None or rng.value.lo > 0 or rng.value.hi < top * kip:
                out.append(f"the {f} load does not reach from 0 to {_kip(top)} kip")
        return out

    def draft(self) -> str:
        """`petra new KIND` with the task's basis, given lines and loads written in."""
        from .templates import TEMPLATES

        _, component, text = TEMPLATES[self.kind]
        lines = text.split("\n")
        start = next(i for i, line in enumerate(lines) if line.startswith(f"{self.kind} {component} {{"))
        end = next(i for i in range(start, len(lines)) if lines[i].strip() == "}")
        body = [line for line in lines[start + 1:end] if _key(line) not in (*GIVEN, "basis")]
        body = [f"  basis {self.basis}", *(f"  {g}" for g in self.given), *body]
        load = next(i for i, line in enumerate(lines) if line.startswith("load "))
        load_end = next(i for i in range(load, len(lines)) if lines[i].strip() == "}")
        loads = ["load task {", *self.load_lines(component), f'  signed "{SIGNER}" source "task {self.id}"', "}"]
        out = lines[:start + 1] + body + lines[end:load] + loads + lines[load_end + 1:]
        return "\n".join(out)


def _key(line: str) -> str:
    return line.split()[0] if line.strip() else ""


def _kip(x: Fraction) -> str:
    return f"{float(x):.3f}".rstrip("0").rstrip(".")


_ON = re.compile(r"^\s*on c1 (\w+) in \[0 kip, ([0-9.]+) kip\]")


def tasks(seed: int, n: int, registry: Registry) -> Iterator[Task]:
    """The first `n` tasks of the generator's stream for `seed`: each design it draws with
    a load the deck passes, outside the detailer-free sample, with no toleranced line and
    of a TASK_KINDS kind, becomes the task of its members and loads. A task's loads carry
    no cycles, so the stream is drawn without cyclic designs, as P2 froze it."""
    from .models.steel.generate import generate

    made, start = 0, 0
    while made < n:
        for g in generate(11, seed, registry, start=start, cyclic=False):
            if made == n:
                return
            if g.kind not in TASK_KINDS or g.expected != "PASS" or g.target != "pass" or g.free or g.toleranced:
                continue
            body = [line.strip() for line in g.text.split("\n") if line.startswith("  ")]
            basis = next(line.split()[1] for line in body if _key(line) == "basis")
            given = tuple(line for line in body if _key(line) in GIVEN)
            loads = tuple((m[1], Fraction(m[2])) for line in g.text.split("\n") if (m := _ON.match(line)))
            made += 1
            yield Task(f"{seed}-{made:03d}", g.kind, basis, given, loads, g.text)
        start += 11


# --- Mass ---------------------------------------------------------------------------------------


def mass(text: str, registry: Registry) -> float:
    """The estimated weight of the connection's own steel, in lb (see the module docstring)."""
    from .models.steel import calc

    design = parse_design(text, "<mass>", registry)
    (name,) = [n for n, c in design.components.items()]
    c = calc.connection(design, name, registry)
    get = c.get

    def inch(key: str) -> float:
        value = getattr(get(key), "quantity", None) or getattr(get(key), "range", None)
        return float(value.value.hi / INCH)

    def thick(spec: Any) -> float:
        value = getattr(spec.thickness, "quantity", None) or getattr(spec.thickness, "range")
        return float(value.value.hi / INCH)

    def area(shape: str) -> float:
        """A rolled shape's section in square inches: an angle's legs and thickness, a WT
        half its parent's area."""
        if shape.startswith("L"):
            d, b, t = (float(registry.constants[f"aisc_shapes_v16.{shape}.{p}"].value.lo / INCH) for p in "dbt")
            return (d + b - t) * t
        from .models.steel.lower import tee_parent
        return float(registry.constants[f"aisc_shapes_v16.{tee_parent(shape)}.A"].value.lo / INCH ** 2) / 2

    def bolts(count: int) -> float:
        d = float(_size(get("bolts").size))
        return count * float(DENSITY) * (math.pi / 4 * d * d * (2 + d) + 2 * 0.866 * (1.5 * d) ** 2 * 0.7 * d)

    def weld(spec: Any, length: float, lines: int = 1) -> float:
        size = float((getattr(spec.size, "quantity", None) or spec.size.range).value.hi / INCH)
        return lines * (spec.sides or 1) * size * size / 2 * length * float(DENSITY)

    rho = float(DENSITY)
    kind = c.kind
    rows = get("rows") or 0
    cols = get("columns") or 1
    height = (rows - 1) * inch("pitch") + 2 * inch("edge_vertical") if rows else 0.0
    bolted_support = get("support_side") == "bolted"
    if kind == "shear_tab":
        width = inch("bolt_line") + (cols - 1) * (inch("gauge") if cols > 1 else 0) + inch("plate_edge")
        return thick(get("plate")) * height * width * rho + bolts(rows * cols) + weld(get("weld"), height)
    if kind in ("double_angle", "single_angle"):
        n = 2 if kind == "double_angle" else 1
        spec = get("angles") if kind == "double_angle" else get("angle")
        return n * area(spec.shape) * height * rho + bolts(rows * cols + (n * rows if bolted_support else 0))
    if kind == "shear_tee":
        return area(get("tee").shape) * height * rho + bolts(rows * cols + (2 * rows if bolted_support else 0))
    if kind == "shear_end_plate":
        return thick(get("plate")) * height * inch("plate_width") * rho + bolts(2 * rows) + weld(get("weld"), height)
    if kind == "seated":
        length = inch("seat_length")
        return (area(get("angle").shape) + area(get("top_angle").shape)) * length * rho + bolts(2 * rows if bolted_support else 0)
    if kind == "stiffened_seat":
        width, length = inch("stiffener_width"), inch("stiffener_length")
        return ((thick(get("plate")) * width * width + thick(get("stiffener")) * width * length) * rho
                + area(get("top_angle").shape) * width * rho + weld(get("weld"), length, 2))
    if kind == "bolt_bracket":
        width = (cols - 1) * inch("gauge") + 2 * inch("plate_edge") + inch("eccentricity")
        return thick(get("plate")) * height * width * rho + bolts(rows * cols)
    if kind == "weld_bracket":
        length = inch("weld_length")
        return thick(get("plate")) * length * inch("eccentricity") * rho + weld(get("weld"), length)
    if kind == "hanger":
        return area(get("tee").shape) * height * rho + bolts(2 * rows)
    raise ValueError(f"no mass estimate for a {kind}")


def _size(size: str) -> Fraction:
    """A Bolts.size as the lowering writes it: "3_4" is 3/4 in, "1_1_8" is 1-1/8 in."""
    parts = [int(p) for p in size.split("_")]
    return Fraction(parts[0]) if len(parts) == 1 else Fraction(parts[0], parts[1]) if len(parts) == 2 \
        else parts[0] + Fraction(parts[1], parts[2])


# --- The loop -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Attempt:
    """One check of the repair: the design's status, the governing check's utilisation on a
    FAIL, and the edit the loop made next, as `input from -> to`."""

    status: str
    utilisation: float | None
    move: str | None


@dataclass
class Run:
    task: Task
    attempts: list[Attempt] = field(default_factory=list)
    passed: str | None = None          # the first design that passed
    optimum: str | None = None         # the minimiser's design
    mass_passed: float | None = None
    mass_optimum: float | None = None
    probes: int = 0                    # designs the minimiser checked
    kept: int = 0                      # designs the minimiser kept, each a PASS
    judged: list[tuple[str, list[str]]] = field(default_factory=list)   # (design, violations) the judge raised

    @property
    def checks_to_pass(self) -> int | None:
        return next((i + 1 for i, a in enumerate(self.attempts) if a.status == "PASS"), None)

    def to_json(self) -> dict[str, Any]:
        return {"task": self.task.id, "kind": self.task.kind, "checks_to_pass": self.checks_to_pass,
                "attempts": [[a.status, a.utilisation, a.move] for a in self.attempts],
                "mass_passed": self.mass_passed, "mass_optimum": self.mass_optimum, "probes": self.probes,
                "kept": self.kept, "judged": [{"design": d, "violations": v} for d, v in self.judged]}


Judge = Callable[[str], list[str]]
"""A design's text -> the conditions an outside judge finds it violates (empty: none)."""


def solve(task: Task, registry: Registry, *, budget: int = 10, judge: Judge | None = None, minimise: bool = True) -> Run:
    run = Run(task)
    sources = (SolverSource(),)
    text = task.draft()
    seen = {text}
    for _ in range(budget):
        checked = check_text(text, f"task-{task.id}.petra", registry, sources)
        if checked.status != "FAIL":
            run.attempts.append(Attempt(checked.status, None, None))
            break
        chosen = _choose(text, checked, seen)
        run.attempts.append(Attempt("FAIL", checked.repair.utilisation if checked.repair else None,
                                    None if chosen is None else chosen[1]))
        if chosen is None:
            break
        text = chosen[0]
        seen.add(text)
    if run.checks_to_pass is None:
        return run
    run.passed = text
    run.mass_passed = mass(text, registry)
    _judge(run, text, judge)
    if minimise:
        _minimise(run, text, registry, sources, judge)
    return run


def _fixed(site: Site) -> bool:
    """A number on a line the job fixes, such as a bracket's eccentricity. The loop never
    edits one, though petra.check's repair may offer it."""
    return site.input.split(".", 1)[1].split()[0] in GIVEN


def _choose(text: str, checked: Checked, seen: set[str]) -> tuple[str, str] | None:
    """The next design from a FAIL's repair, as the module docstring orders the moves."""
    if checked.repair is None:
        return None
    moves = [m for m in checked.repair.moves if not _fixed(m.site)]
    clearing = sorted((m for m in moves if m.clears is not None),
                      key=lambda m: (m.clears.status != "PASS", len(m.clears.fails)))
    options = [(m, m.clears.to) for m in clearing] + [(m, m.step.to) for m in moves]
    for m, to in options:
        out = edit(text, m.site, to)
        if out not in seen:
            return out, f"{m.site.input} {m.site.text} -> {to}"
    return None


def _judge(run: Run, text: str, judge: Judge | None) -> None:
    if judge is not None:
        found = judge(text)
        if found:
            run.judged.append((text, found))


def _passes(text: str, registry: Registry, sources: tuple, run: Run) -> bool:
    run.probes += 1
    return check_text(text, "<minimise>", registry, sources, moves=False).status == "PASS"


def _minimise(run: Run, text: str, registry: Registry, sources: tuple, judge: Judge | None) -> None:
    current, weight = text, mass(text, registry)
    improved = True
    while improved:
        improved = False
        for candidate in _lighter(current, registry, weight):
            better = _farthest(candidate, current, weight, registry, sources, run)
            if better is not None:
                current, weight = better, mass(better, registry)
                run.kept += 1
                _judge(run, current, judge)
                improved = True
                break
    run.optimum, run.mass_optimum = current, weight


@dataclass(frozen=True)
class _Edit:
    """One way to make the design lighter: a number stepped in `direction`, or a shape
    swapped for each of the lighter `shapes` of its family, lightest first."""

    site: Site
    direction: int = 0
    shapes: tuple[str, ...] = ()


def _lighter(text: str, registry: Registry, weight: float) -> Iterator[_Edit]:
    for site in sites(text):
        if _fixed(site):
            continue
        for direction in (-1, 1):
            first = next(_accepted(text, site, direction, registry), None)
            if first is not None and first[1] < weight - 1e-9:
                yield _Edit(site, direction)
                break
    for site in shape_sites(text, registry):
        swaps = sorted((m, shape) for shape in family(site.text, registry)
                       if (m := _mass_or_none(edit(text, site, shape), registry)) is not None and m < weight - 1e-9)
        if swaps:
            yield _Edit(site, shapes=tuple(shape for _, shape in swaps))


def _mass_or_none(text: str, registry: Registry) -> float | None:
    try:
        return mass(text, registry)
    except (*INPUT_ERRORS, KeyError, AttributeError, TypeError, ValueError):
        return None


def _farthest(e: _Edit, text: str, weight: float, registry: Registry, sources: tuple, run: Run) -> str | None:
    """The lightest passing design along one edit: for a site, the farthest step that
    passes, doubling while it does; for a shape line, the lightest shape that passes."""
    if e.shapes:
        return next((c for shape in e.shapes if _passes(c := edit(text, e.site, shape), registry, sources, run)), None)
    best, tried = None, 0
    for i, (candidate, m) in enumerate(_accepted(text, e.site, e.direction, registry)):
        if i != tried:
            continue
        if m >= weight - 1e-9 or not _passes(candidate, registry, sources, run):
            break
        best, tried = candidate, 2 * i + 1
    return best


def _accepted(text: str, site: Site, direction: int, registry: Registry) -> Iterator[tuple[str, float]]:
    """The site's ladder in `direction`, kept to the designs that lower, with their mass."""
    for _, number in ladder(site, direction):
        candidate = edit(text, site, number)
        m = _mass_or_none(candidate, registry)
        if m is not None:
            yield candidate, m
