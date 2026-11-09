"""The two component kinds a design names: part and assembly. Trusted.

Each lowerer checks its block against its Grammar and the registry and returns a typed
model, or raises ComponentError listing every problem. Lengths in the typed models are
exact millimetres in the frame of the body that declares them; build.py states them in
metres. A mesh file resolves against the design file's directory; a design checked as
text with no file (the MCP tool) must name absolute paths. docs/parts.md shows a design
with both kinds.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable, Literal

from ...ir import Arg, Bound, Component, Design, Fixed, Input, Ref, Rel, Span, Text, Vec
from ...registry import OutsideMakeableSet, PartKind, ProcessKind, Registry
from ...units import DIMENSIONLESS, LENGTH, MASS, TEMPERATURE, Dim
from ..base import SIGNED_BOUND, ComponentError, Field, Grammar
from . import exact
from .mesh import Mesh, MeshError, Point, Unit, read_mesh
from .space import Axis, Placement, turn

Q = Fraction
ROLES = ("clear", "tap", "form", "insert", "press")
PROCESS_KINDS = (ProcessKind.PRINT, ProcessKind.POWDER, ProcessKind.SHEET, ProcessKind.MILL)


@dataclass(frozen=True)
class Hole:
    """A hole the part declares. The mesh holds the geometry; the line says what the hole
    is for, so fit.hole can test the mesh against it and the fastener and insert rules
    can read it."""

    id: str
    at: Point                          # the hole's mouth on the part's surface, mm
    along: Axis                        # the direction the hole runs into the part
    diameter: Q                        # nominal, mm
    depth: Q | None                    # mm; None: through the part
    role: Literal["clear", "tap", "form", "insert", "press"]
    insert: str | None                 # the registry insert a role-insert hole takes
    countersink: Q | None              # diameter at the mouth of a 90 degree countersink, mm


@dataclass(frozen=True)
class PartDesign:
    """One part: its mesh, its material and how it is made. A part with a `mass` line is
    bought: its mass is the signed bound, not its volume times a density."""

    name: str
    mesh: Mesh
    material: str
    preset: str | None                 # registry process preset id
    finish: str | None                 # registry coating id
    tolerance: Input | None            # signed profile tolerance, m; replaces the preset's row
    hole_shrink: Input | None          # signed diametral undersize of modelled holes, m
    fill: Input | None                 # signed mass fraction of a solid part, for printed infill
    mass: Input | None                 # signed mass of a bought part, kg
    heat: Input | None                 # signed rise above ambient at the part, degC
    cg: Point | None                   # the stated centre of mass in the part's frame, mm
    holes: tuple[Hole, ...]
    span: Span

    @property
    def kind(self) -> ProcessKind | None:
        return None if self.preset is None else ProcessKind(self.preset.split(".")[1])


@dataclass(frozen=True)
class Place:
    body: PartDesign
    placement: Placement               # exact; the turn takes the body's top and front to the named axes


@dataclass(frozen=True)
class Fasten:
    """A screw through a stack of holes, head side first; the last hole is the one the
    thread enters. A hole is (body, hole id)."""

    id: str
    screw: str
    stack: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Insert:
    """The body arrives at its place moving `travel` mm along `along`."""

    body: str
    along: Axis
    travel: Q


@dataclass(frozen=True)
class Apart:
    """Two bodies that keep `least` mm apart beyond their tolerances."""

    a: str
    b: str
    least: Q


@dataclass(frozen=True)
class Press:
    """A pin body pressed into a declared press hole. The pair may overlap, and fit.press
    holds the interference to the declared range."""

    id: str
    pin: str
    body: str
    hole: str
    diameter: Q                        # the pin's nominal diameter at the fit, mm
    lo: Q                              # least diametral interference, mm
    hi: Q                              # greatest diametral interference, mm


@dataclass(frozen=True)
class Assembly:
    name: str
    places: tuple[Place, ...]          # in assembly order; the first is the base
    inserts: tuple[Insert, ...]
    fastens: tuple[Fasten, ...]
    gaps: tuple[Apart, ...]
    presses: tuple[Press, ...]
    span: Span

    def place(self, body: str) -> Place:
        return next(p for p in self.places if p.body.name == body)

    def hole(self, body: str, hole: str) -> Hole:
        return next(h for h in self.place(body).body.holes if h.id == hole)


_POINT = "(<x>, <y>, <z>)"
_AXIS = "<top|bottom|left|right|front|back>"
_MATERIALS = ("polymer.", "aluminium.", "steel.", "stainless.")
_PRESETS = ("process.print.", "process.powder.", "process.sheet.", "process.mill.")

PART_GRAMMAR = Grammar(
    required=(
        Field("mesh", '"<file>" sha256 "<hex>" units <mm|inch>', "", (),
              "the part's closed surface, an STL or 3MF file, pinned by its hash; coordinates are read exactly"),
        Field("material", "<registry material id>", "", _MATERIALS, "what the part is made of"),
    ),
    optional=(
        Field("process", "<registry process id>", "", _PRESETS,
              "how the part is made: its tolerance, hole shrink and build volume; a bought part names none"),
        Field("finish", "<registry coating id>", "", ("process.anodize_ii", "process.powder_coat"),
              "a coating whose buildup every fit rule adds to the part's surfaces"),
        Field("tolerance", SIGNED_BOUND, "length", (), "the profile tolerance, replacing the process preset's"),
        Field("hole_shrink", SIGNED_BOUND, "length", (), "how much smaller modelled holes come out, diametral"),
        Field("fill", SIGNED_BOUND, "dimensionless", (), "the part's mass over a solid part's, for printed infill"),
        Field("mass", SIGNED_BOUND, "mass", (), "a bought part's mass; without it the mass is volume times density"),
        Field("heat", SIGNED_BOUND, "temperature", (), "how far a local heat source lifts the part above ambient"),
        Field("cg", _POINT, "length", (), "the centre of mass of a bought or infilled part, in its own frame"),
        Field("hole", f"<id> at {_POINT} along {_AXIS} diameter <length> [depth <length>] "
              "[clear|tap|form|press|insert <registry insert id>] [countersink <length>]", "length", ("insert.",),
              "a hole and what it is for; through the part when no depth is given"),
    ),
    target="<part>",
    loads=(),
)

ASSEMBLY_GRAMMAR = Grammar(
    required=(
        Field("place", f"<part> at {_POINT} facing {_AXIS} {_AXIS}", "length", (),
              "puts a part at a point, its top and front along the two axes; the first is the base"),
    ),
    optional=(
        Field("insert", f"<part> along {_AXIS} from <length>", "length", (),
              "the part arrives at its place moving along the axis over the length; every part but the base has one"),
        Field("fasten", "<id> <registry screw id> through <part>.<hole> [<part>.<hole> ...] into <part>.<hole>",
              "", ("screw.",), "a screw through clear holes, head side first, into the hole its thread enters"),
        Field("gap", "<part> <part> [<length>]", "length", (), "two parts that keep apart beyond their tolerances"),
        Field("press", "<id> <part> into <part>.<hole> diameter <length> interference <length> to <length>",
              "length", (), "a pin part pressed into a press hole, with its diametral interference range"),
    ),
    target="<assembly>",
    loads=(),
)

PART_QOIS = {"mass": MASS}
ASSEMBLY_QOIS = {"mass": MASS, "cg_x": LENGTH, "cg_y": LENGTH, "cg_z": LENGTH}

Say = Callable[[str], None]


def _say(problems: list[str], span: Span, what: str) -> Say:
    return lambda message: problems.append(f"{span.path}:{span.line}:{span.col}: {what}: {message}")


def _word(arg: Arg | None) -> str | None:
    return arg.parts[0] if isinstance(arg, Ref) and len(arg.parts) == 1 else None


def _id(arg: Arg | None) -> str | None:
    return ".".join(arg.parts) if isinstance(arg, Ref) else None


def _mm(arg: Arg | None) -> Q | None:
    if isinstance(arg, Fixed) and arg.quantity.dim == LENGTH and arg.quantity.value.lo == arg.quantity.value.hi:
        return arg.quantity.value.lo * 1000
    return None


def _point(arg: Arg | None) -> Point | None:
    if not isinstance(arg, Vec) or len(arg.items) != 3:
        return None
    if any(q.dim != LENGTH or q.value.lo != q.value.hi for q in arg.items):
        return None
    return tuple(q.value.lo * 1000 for q in arg.items)


def _axis(arg: Arg | None) -> Axis | None:
    word = _word(arg)
    return Axis[word.upper()] if word is not None and word.upper() in Axis.__members__ else None


def _bound(name: str, args: tuple[Arg, ...], dim: Dim, say: Say) -> Input | None:
    bound = args[0] if len(args) == 1 else None
    if not (isinstance(bound, Bound) and bound.range.dim == dim):
        say(f"needs one signed bound in {'mm' if dim == LENGTH else 'g or kg' if dim == MASS else 'degC' if dim == TEMPERATURE else 'a fraction'}")
        return None
    if bound.range.value.lo < 0:
        say("is not negative")
        return None
    return Input(name, bound.range, bound.signature, bound.kind, bound.span, bound.mean)


def _resolve(text: str, design: Design) -> Path:
    path = Path(text)
    if path.is_absolute():
        return path
    return Path(design.path).parent / path


_PART_MEMO: dict[tuple[int, str], tuple[Design, PartDesign]] = {}
_SURFACE: dict[int, tuple[Mesh, str | None]] = {}


def lower_part(component: Component, design: Design, registry: Registry) -> PartDesign:
    """Check a part block and read its mesh. Raises ComponentError for a missing or
    repeated line, an unknown registry id, a mesh the reader refuses or whose surface
    crosses itself (exact.surface_problem), a hole whose mouth lies outside the mesh's
    extent, and a claim on a quantity a part does not have."""
    key = (id(design), component.name)
    if key in _PART_MEMO and _PART_MEMO[key][0] is design:
        return _PART_MEMO[key][1]
    problems: list[str] = []
    name = component.name
    seen: dict[str, Arg] = {}
    one: dict[str, tuple[Arg, ...]] = {}
    holes: list[Hole] = []
    inputs: dict[str, Input] = {}
    dims = {"tolerance": LENGTH, "hole_shrink": LENGTH, "fill": DIMENSIONLESS, "mass": MASS, "heat": TEMPERATURE}
    for attr in component.attrs:
        say = _say(problems, attr.span, f"{name}.{attr.key}")
        if attr.key in ("mesh", "material", "process", "finish", "cg") or attr.key in dims:
            if attr.key in one:
                say("is given twice")
                continue
            one[attr.key] = attr.args
            if attr.key in dims:
                found = _bound(f"{name}.{attr.key}", attr.args, dims[attr.key], say)
                if found is not None:
                    inputs[attr.key] = found
        elif attr.key == "hole":
            hole = _hole(attr.args, registry, say)
            if hole is not None:
                if any(h.id == hole.id for h in holes):
                    say(f"hole {hole.id} is declared twice")
                holes.append(hole)
        else:
            say(f"unknown attribute; a part takes {', '.join(PART_GRAMMAR.names)}")
    here = _say(problems, component.span, name)
    for key in ("mesh", "material"):
        if key not in one:
            here(f"a part needs a {key} line")
    mesh = _mesh(one.get("mesh"), design, _say(problems, component.span, f"{name}.mesh")) if "mesh" in one else None
    material = _id(one["material"][0]) if one.get("material") else None
    if "material" in one:
        try:
            registry.material(material or "")
        except OutsideMakeableSet as e:
            here(str(e))
    preset = _id(one["process"][0]) if one.get("process") else None
    if preset is not None:
        found = registry.processes.get(preset)
        if found is None or found.kind not in PROCESS_KINDS:
            here(f"process {preset} is not a print, powder, sheet or mill preset")
    finish = _id(one["finish"][0]) if one.get("finish") else None
    if finish is not None:
        found = registry.processes.get(finish)
        if found is None or found.kind is not ProcessKind.COATING or "buildup" not in found.props:
            here(f"finish {finish} is not a registry coating with a buildup row")
    cg = _point(one["cg"][0]) if one.get("cg") and len(one["cg"]) == 1 else None
    if "cg" in one and cg is None:
        here("cg reads cg (<x>, <y>, <z>) in mm")
    if "fill" in inputs and inputs["fill"].range.value.hi > 1:
        here("a fill is a fraction of a solid part, at most 1")
    if mesh is not None:
        lo, hi = mesh.bounds()
        for h in holes:
            if not all(lo[k] <= h.at[k] <= hi[k] for k in range(3)):
                here(f"hole {h.id}'s mouth {tuple(float(c) for c in h.at)} lies outside the mesh's extent")
    _check_claims(name, PART_QOIS, design, problems)
    if problems:
        raise ComponentError(tuple(problems))
    part = PartDesign(name, mesh, material, preset, finish, inputs.get("tolerance"), inputs.get("hole_shrink"),
                      inputs.get("fill"), inputs.get("mass"), inputs.get("heat"), cg, tuple(holes), component.span)
    _PART_MEMO[key] = (design, part)
    return part


def _mesh(args: tuple[Arg, ...] | None, design: Design, say: Say) -> Mesh | None:
    shape = (args is not None and len(args) == 5 and isinstance(args[0], Text) and _word(args[1]) == "sha256"
             and isinstance(args[2], Text) and _word(args[3]) == "units" and _word(args[4]) in ("mm", "inch"))
    if not shape:
        say('reads `mesh "<file>" sha256 "<hex>" units <mm|inch>`')
        return None
    unit = Unit.MM if _word(args[4]) == "mm" else Unit.INCH
    try:
        mesh = read_mesh(_resolve(args[0].value, design), args[2].value, unit)
    except MeshError as e:
        say(str(e))
        return None
    if id(mesh) not in _SURFACE or _SURFACE[id(mesh)][0] is not mesh:
        _SURFACE[id(mesh)] = (mesh, exact.surface_problem(mesh))
    problem = _SURFACE[id(mesh)][1]
    if problem is not None:
        say(f"{mesh.path}: {problem}")
        return None
    return mesh


def _hole(args: tuple[Arg, ...], registry: Registry, say: Say) -> Hole | None:
    usage = (f"reads `hole <id> at {_POINT} along {_AXIS} diameter <length> [depth <length>] "
             "[clear|tap|form|press|insert <registry insert id>] [countersink <length>]`")
    if len(args) < 7 or _word(args[1]) != "at" or _word(args[3]) != "along" or _word(args[5]) != "diameter":
        say(usage)
        return None
    hid, at, along, diameter = _word(args[0]), _point(args[2]), _axis(args[4]), _mm(args[6])
    if hid is None or at is None or along is None or diameter is None or diameter <= 0:
        say(usage)
        return None
    rest = list(args[7:])
    depth = role = insert = countersink = None
    while rest:
        word = _word(rest.pop(0))
        if word == "depth" and rest and depth is None:
            depth = _mm(rest.pop(0))
            if depth is None or depth <= 0:
                say("depth is a positive length")
                return None
        elif word == "countersink" and rest and countersink is None:
            countersink = _mm(rest.pop(0))
            if countersink is None or countersink <= diameter:
                say("a countersink is wider than its hole")
                return None
        elif word in ROLES and role is None:
            role = word
            if word == "insert":
                insert = _id(rest.pop(0)) if rest else None
                try:
                    registry.part(insert or "", PartKind.INSERT)
                except OutsideMakeableSet as e:
                    say(str(e))
                    return None
        else:
            say(usage)
            return None
    return Hole(hid, at, along, diameter, depth, role or "clear", insert, countersink)


def lower_assembly(component: Component, design: Design, registry: Registry) -> Assembly:
    """Check an assembly block. Each body it places is a part block of the design, placed
    once. Every body but the first has an insert line, so each part's way in is checked.
    Raises ComponentError for an unknown part, a turn whose two axes are not
    perpendicular, a fasten or press naming an unknown hole, a screw or a press into a
    hole of the wrong role, and a gap naming one part twice."""
    problems: list[str] = []
    name = component.name
    places: list[Place] = []
    inserts: list[Insert] = []
    fastens: list[Fasten] = []
    gaps: list[Apart] = []
    presses: list[Press] = []
    parts: dict[str, PartDesign] = {}

    def part(word: str | None, say: Say) -> PartDesign | None:
        c = design.components.get(word or "")
        if c is None or c.kind != "part":
            say(f"{word} is not a part of this design")
            return None
        if word not in parts:
            try:
                parts[word] = lower_part(c, design, registry)
            except ComponentError:
                return None
        return parts[word]

    for attr in component.attrs:
        say = _say(problems, attr.span, f"{name}.{attr.key}")
        a = attr.args
        if attr.key == "place":
            if len(a) != 6 or _word(a[1]) != "at" or _point(a[2]) is None or _word(a[3]) != "facing" \
                    or _axis(a[4]) is None or _axis(a[5]) is None:
                say(f"reads `place <part> at {_POINT} facing {_AXIS} {_AXIS}`")
                continue
            body = part(_word(a[0]), say)
            if body is None:
                continue
            if any(p.body.name == body.name for p in places):
                say(f"{body.name} is placed twice")
                continue
            try:
                places.append(Place(body, Placement(turn(_axis(a[4]), _axis(a[5])), _point(a[2]))))
            except ValueError as e:
                say(str(e))
        elif attr.key == "insert":
            if len(a) != 5 or _word(a[1]) != "along" or _axis(a[2]) is None or _word(a[3]) != "from" \
                    or _mm(a[4]) is None or _mm(a[4]) <= 0:
                say(f"reads `insert <part> along {_AXIS} from <length>`")
                continue
            inserts.append(Insert(_word(a[0]), _axis(a[2]), _mm(a[4])))
        elif attr.key == "fasten":
            ids = [_id(x) for x in a]
            if len(a) < 5 or _word(a[2]) != "through" or "into" not in ids[3:] or ids.index("into", 3) != len(a) - 2:
                say("reads `fasten <id> <registry screw id> through <part>.<hole> [...] into <part>.<hole>`")
                continue
            try:
                registry.part(ids[1] or "", PartKind.SCREW)
            except OutsideMakeableSet as e:
                say(str(e))
                continue
            stack = tuple(tuple(x.parts) if isinstance(x, Ref) and len(x.parts) == 2 else None
                          for x in (*a[3:-2], a[-1]))
            if any(s is None for s in stack):
                say("names each hole as <part>.<hole>")
                continue
            fastens.append(Fasten(_word(a[0]) or "", ids[1], stack))
        elif attr.key == "gap":
            least = _mm(a[2]) if len(a) == 3 else Fraction(0)
            if len(a) not in (2, 3) or least is None or least < 0 or _word(a[0]) is None or _word(a[0]) == _word(a[1]):
                say("reads `gap <part> <other part> [<length>]`")
                continue
            gaps.append(Apart(_word(a[0]), _word(a[1]), least))
        elif attr.key == "press":
            ok = (len(a) == 10 and _word(a[2]) == "into" and isinstance(a[3], Ref) and len(a[3].parts) == 2
                  and _word(a[4]) == "diameter" and _word(a[6]) == "interference" and _word(a[8]) == "to")
            vals = (_mm(a[5]), _mm(a[7]), _mm(a[9])) if ok else (None,)
            if not ok or any(v is None for v in vals) or not (0 <= vals[1] <= vals[2]):
                say("reads `press <id> <part> into <part>.<hole> diameter <length> interference <length> to <length>`, "
                    "the interference range rising from at least 0")
                continue
            presses.append(Press(_word(a[0]) or "", _word(a[1]) or "", a[3].parts[0], a[3].parts[1], *vals))
        else:
            say(f"unknown attribute; an assembly takes {', '.join(ASSEMBLY_GRAMMAR.names)}")
    here = _say(problems, component.span, name)
    placed = {p.body.name: p for p in places}
    if not places:
        here("an assembly places at least one part")
    for ins in inserts:
        if ins.body not in placed:
            here(f"insert names {ins.body}, which no place line puts in the assembly")
        elif places[0].body.name == ins.body:
            here(f"{ins.body} is the base: it is placed first and arrives nowhere")
    moved = [i.body for i in inserts]
    for p in places[1:]:
        if moved.count(p.body.name) != 1:
            here(f"{p.body.name} needs exactly one insert line saying how it arrives at its place")

    def hole(body: str, hid: str) -> Hole | None:
        if body not in placed:
            here(f"{body} is not placed in the assembly")
            return None
        found = next((h for h in placed[body].body.holes if h.id == hid), None)
        if found is None:
            here(f"{body} declares no hole {hid}")
        return found

    for f in fastens:
        holes = [hole(b, h) for b, h in f.stack]
        if None in holes:
            continue
        if any(h.role != "clear" for h in holes[:-1]):
            here(f"fasten {f.id}: a screw passes clear holes before the last")
        if holes[-1].role not in ("tap", "form", "insert"):
            here(f"fasten {f.id}: the last hole is tap, form or insert, so the thread has something to enter")
        if len({b for b, _ in f.stack}) != len(f.stack):
            here(f"fasten {f.id}: each part appears once in the stack")
    for g in gaps:
        for b in (g.a, g.b):
            if b not in placed:
                here(f"gap names {b}, which is not placed")
    for p in presses:
        h = hole(p.body, p.hole)
        if p.pin not in placed:
            here(f"press {p.id}: {p.pin} is not placed")
        if h is not None and h.role != "press":
            here(f"press {p.id}: {p.body}.{p.hole} is not a press hole")
    _check_claims(name, ASSEMBLY_QOIS, design, problems)
    if problems:
        raise ComponentError(tuple(problems))
    return Assembly(name, tuple(places), tuple(inserts), tuple(fastens), tuple(gaps), tuple(presses), component.span)


def _check_claims(name: str, qois: dict[str, Dim], design: Design, problems: list[str]) -> None:
    for claim in design.claims:
        if claim.qoi.path[0] != name:
            continue
        say = _say(problems, claim.span, f"claim {claim.name}")
        if len(claim.qoi.path) != 1 or claim.qoi.name not in qois:
            say(f"a claim on {name} names one of {', '.join(qois)}, as in {name}.mass")
        elif claim.bound.dim != qois[claim.qoi.name]:
            say(f"{claim.qoi.name} is bounded by a {'mass' if qois[claim.qoi.name] == MASS else 'length'}")
        elif claim.under:
            say("a parts claim holds under no load case")
    for case in design.loads.values():
        for entry in case.entries:
            if entry.target[0] == name:
                _say(problems, case.span, f"load {case.name}")(f"{name} takes no loads in v0")
    for claim in design.probability_claims:
        if getattr(claim.event, "qoi", None) is not None and claim.event.qoi.path[0] == name:
            _say(problems, claim.span, f"claim {claim.name}")("v0 states no probability claim on parts")
