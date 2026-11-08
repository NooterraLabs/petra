"""The three component kinds a design names: part, pcb and assembly. Trusted.

Each lowerer checks its block against its Grammar and the registry and returns a typed
model, or raises ComponentError listing every problem. Lengths in the typed models are
exact millimetres in the frame of the body that declares them; build.py states them in
metres. A file a block names resolves against the design file's directory; a design
checked as text with no file (the MCP tool) must name absolute paths. docs/parts.md
shows a design with all three kinds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from ...ir import Component, Design, Input, Span
from ...kernel import Q
from ...registry import Registry
from ..base import SIGNED_BOUND, Field, Grammar
from .deck import Override
from .kicad import Board
from .mesh import Mesh, Point
from .space import Axis, Placement


@dataclass(frozen=True)
class Hole:
    """A hole the part declares. The geometry is the mesh's; the declaration says what the
    hole is for, so fit.hole can test it with a pin and fit.grip can read what a screw
    entering it bites into."""

    id: str
    at: Point                          # the hole's mouth on the part's surface
    along: Axis                        # the direction the hole runs into the part
    diameter: Q                        # nominal, mm
    depth: Q | None                    # mm; None: through the part
    role: Literal["clear", "tap", "form", "insert"]   # a screw passes, cuts a thread, forms one, or meets a heat-set insert


@dataclass(frozen=True)
class Seat:
    """A face a screw head or washer bears on. `ring` is the registry id of the screw or
    washer whose bearing ring must lie on the face."""

    id: str
    at: Point                          # the ring's centre
    facing: Axis                       # the face's outward normal
    ring: str                          # "screw.<id>" or "washer.<id>"


@dataclass(frozen=True)
class PartDesign:
    """One part: its mesh, what it is made of, and, when it names a process, how it is made.
    A part without a process is checked for fit only, and the readout says so."""

    name: str
    mesh: Mesh
    material: str                      # registry material id
    preset: str | None                 # registry process preset id
    directions: tuple[Axis, ...]       # build (print, powder), normal (sheet), setups (mill) or pull (mold), in the part's frame
    stock: tuple[Point, Point] | None  # the blank to mill from; None: the part's extent
    holes: tuple[Hole, ...]
    seats: tuple[Seat, ...]
    overrides: tuple[Override, ...]
    budgets: Mapping[str, Input]       # "setups.budget" or "side_actions.budget" -> a signed count
    span: Span


@dataclass(frozen=True)
class PcbDesign:
    """One circuit board read from its KiCad file. Every footprint's height is a premise:
    its own `height` line, the footprint's Height property, or the `height others` line,
    in that order. A footprint with none of them leaves fit.keepout a Gap that names it."""

    name: str
    board: Board
    preset: str                        # "process.pcb.<id>": outline and drill tolerances, for fit only
    heights: Mapping[str, Input]       # reference designator -> signed height above its side, m
    others: Input | None
    span: Span


@dataclass(frozen=True)
class Place:
    body: str                          # a part or pcb block of the design
    placement: Placement               # exact; the turn takes the body's top and front to the named axes


@dataclass(frozen=True)
class Fasten:
    """A screw through a stack of holes, from the head side to the thread. A part's hole is
    named by its hole line's id, a board's by its footprint reference ("main.H1")."""

    id: str
    screw: str                         # registry screw id
    washer: str | None                 # registry washer id under the head
    stack: tuple[tuple[str, str], ...] # (body, hole id), head side first; the last is the one the thread enters


@dataclass(frozen=True)
class Insert:
    """The body travels `travel` mm along `along` into its placed position. fit.insert
    sweeps it back out along the opposite direction."""

    body: str
    along: Axis
    travel: Q


@dataclass(frozen=True)
class Access:
    """A mating plug, a rectangle `width` by `height` mm across its travel, reaching the
    point `at` along `along` from outside the assembly."""

    id: str
    width: Q
    height: Q
    at: Point                          # in the assembly's frame
    along: Axis


@dataclass(frozen=True)
class Apart:
    """Two bodies that must not touch. `least` None reads fit.clearance from both bodies'
    presets and takes the larger."""

    a: str
    b: str
    least: Q | None


@dataclass(frozen=True)
class Guard:
    """No ball of diameter `sphere` may travel from the `outside` box to the `hazard` box.
    The diameter comes from a code the owner names (IEC 60529, ISO 13857) and is signed,
    because no code table ships with Petra yet."""

    id: str
    sphere: Input                      # m
    outside: tuple[Point, Point]
    hazard: tuple[Point, Point]


@dataclass(frozen=True)
class Opening:
    """A declared opening of a body in a guard: its least width across, mm. A hole, a slot
    or the gap between two bars passes the guard's ball when it is at least the ball's
    diameter at the process's widest tolerance."""

    id: str
    guard: str
    body: str
    shape: Literal["hole", "slot", "bars"]
    width: Q


@dataclass(frozen=True)
class Assembly:
    name: str
    places: tuple[Place, ...]
    fastens: tuple[Fasten, ...]
    inserts: tuple[Insert, ...]
    accesses: tuple[Access, ...]
    gaps: tuple[Apart, ...]
    guards: tuple[Guard, ...]
    openings: tuple[Opening, ...]
    span: Span


_POINT = "(<x>, <y>, <z>)"
_AXIS = "<top|bottom|left|right|front|back>"
_MATERIALS = ("steel.", "stainless.", "aluminium.", "polymer.", "composite.")
_PRESETS = ("process.print.", "process.powder.", "process.sheet.", "process.mill.", "process.mold.")

PART_GRAMMAR = Grammar(
    required=(
        Field("mesh", '"<file>" sha256 "<hex>" units <mm|inch>', "", (),
              "the part's closed surface, an STL or 3MF file, pinned by its hash; coordinates are read exactly"),
        Field("material", "<registry material id>", "", _MATERIALS, "what the part is made of"),
    ),
    optional=(
        Field("process", "<registry process id>", "", _PRESETS,
              "how the part is made; without it only the fit rules apply to it"),
        Field("build", _AXIS, "", (), "the printer's up direction in the part's frame (print, powder)"),
        Field("normal", _AXIS, "", (), "the sheet's normal in the part's frame (sheet)"),
        Field("setups", f"{_AXIS} [{_AXIS} ...]", "", (), "the directions the cutter may come from (mill)"),
        Field("pull", _AXIS, "", (), "the direction the mold opens; its opposite is the other half (mold)"),
        Field("stock", f"{_POINT} to {_POINT}", "length", (), "the blank to mill from; default the part's extent"),
        Field("hole", f"<id> at {_POINT} along {_AXIS} diameter <length> [depth <length>] [clear|tap|form|insert]",
              "length", (), "a hole and what it is for; through the part when no depth is given"),
        Field("seat", f"<id> at {_POINT} facing {_AXIS} ring <registry screw or washer id>", "length",
              ("screw.", "washer."), "a face the head or washer bears on"),
        Field("override", f"<row> {SIGNED_BOUND}", "", (), "replaces one row of the process preset for this part"),
        Field("budget", f"<setups|side_actions> {SIGNED_BOUND}", "", (),
              "the most setups or side actions the maker accepts; past it the costlier rule fails"),
    ),
    target="<part>",
    loads=(),
)

PCB_GRAMMAR = Grammar(
    required=(
        Field("file", '"<file.kicad_pcb>" sha256 "<hex>"', "", (), "the board, KiCad 6 or later, pinned by its hash"),
        Field("process", "<registry process id>", "", ("process.pcb.",), "the board maker's outline and drill tolerances"),
    ),
    optional=(
        Field("height", f"<reference|others> {SIGNED_BOUND}", "length", (),
              "a component's height above its side of the board; others covers every footprint without its own"),
    ),
    target="<pcb>",
    loads=(),
)

ASSEMBLY_GRAMMAR = Grammar(
    required=(
        Field("place", f"<body> at {_POINT} facing {_AXIS} {_AXIS}", "length", (),
              "puts a part or board at a point, its top and front along the two axes"),
    ),
    optional=(
        Field("fasten", "<id> <registry screw id> [washer <registry washer id>] through <body>.<hole> "
              "[<body>.<hole> ...] into <body>.<hole>", "", ("screw.", "washer."),
              "a screw through a stack of holes, head side first"),
        Field("insert", f"<body> along {_AXIS} from <length>", "length", (),
              "the body arrives at its place travelling along the axis over the length"),
        Field("access", f"<id> box (<width>, <height>) at {_POINT} along {_AXIS}", "length", (),
              "a mating plug reaches the point from outside along the axis"),
        Field("gap", "<body> <body> [<length>]", "length", (), "two bodies that must not touch"),
        Field("guard", f"<id> sphere {SIGNED_BOUND} from {_POINT} to {_POINT} hazard {_POINT} to {_POINT}",
              "length", (), "no ball of the signed diameter reaches the hazard box from the outside box"),
        Field("opening", "<id> guard <guard> on <body> <hole|slot|bars> <length>", "length", (),
              "a declared opening of a body in a guard, by its least width"),
    ),
    target="<assembly>",
    loads=(),
)


def lower_part(component: Component, design: Design, registry: Registry) -> PartDesign:
    """Check a part block and read its mesh. Raises ComponentError for a missing or
    repeated required line, an unknown material or preset, a preset of a kind the part's
    direction lines do not suit (build without a print or powder preset, two pulls), a
    hole or seat whose point is outside the mesh's extent, an override of a row the preset
    lacks or with the wrong unit, a waiver on an impossible rule, a mesh whose hash does
    not match, and a mesh whose surface crosses itself (exact.self_crossing names the two
    triangles). Memoised on (design, component name)."""
    raise NotImplementedError


def lower_pcb(component: Component, design: Design, registry: Registry) -> PcbDesign:
    """Check a pcb block and read its board with kicad.read_board. Raises ComponentError
    for a height line naming a reference the board lacks, a reference given two heights,
    and a board the reader refuses."""
    raise NotImplementedError


def lower_assembly(component: Component, design: Design, registry: Registry) -> Assembly:
    """Check an assembly block. Each body it places is a part or pcb block of the design,
    lowered with lower_part or lower_pcb (memoised), and placed at most once. Raises
    ComponentError for an unknown body, a turn whose two axes are not perpendicular, a
    fasten whose holes are unknown or whose last hole is a clear hole, an opening naming
    an unknown guard, and a gap naming one body twice."""
    raise NotImplementedError
