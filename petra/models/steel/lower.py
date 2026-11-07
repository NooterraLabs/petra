"""Lowering for the steel-connection deck: attribute lines -> a typed Conn. Trusted.

Every connection kind reads the same attribute grammar, one attribute per line. FIELDS
gives each line's form and meaning, KIND_SPECS the lines each kind requires and allows,
and `grammar(kind)` joins the two into the kind's Grammar (`petra kinds steel` prints it).

An omitted optional line means the feature is absent, as ABSENT says: one bolt column, a
conventional plate, a single force, standard holes, painted steel, bearing deformation a
design consideration. A line whose absence a check would have to guess is required where
that check reads it (WELD_SIDES, SET_BACK, and J10.4's inputs; docs/principles.md D4).

A <len> is a length (Fixed), a signed bound `in [lo, hi] signed "..." source "..."`
(an ir.Input named "<conn>.<field>", which the pipeline's premise book finds in the
typed model), or `param NAME`. A count is a whole number on a line of its own. Shapes are
designations: W18x50, L4x3_1_2x3_8 (L4x3-1/2x3/8), WT9x25 (cut from W18x50).

Load fields per kind: LOAD_FIELDS. Claims name `<conn>.<qoi>`, a mode's short name
(QOIS in vocab.py), bounded by a dimensionless utilisation.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from types import MappingProxyType
from typing import Callable, Mapping, Union

from ...ir import Arg, Bound, Component, Design, Exceeds, Fixed, Input, ParamRef, Ref, Span, Text
from ...registry import OutsideMakeableSet, Registry
from ...registry.steel import INCH, STOCK_PLATE
from ...units import DIMENSIONLESS, FORCE, LENGTH, Dim
from ..base import ComponentError, Field, Grammar

Geo = Union[Fixed, ParamRef, Input]
"""A design length: a fixed value, a scope parameter, or a signed toleranced bound."""


@dataclass(frozen=True, slots=True)
class Member:
    shape: str            # "W18x50"
    grade: str            # "steel.A992"
    face: str | None   # a support's connected face: "flange" | "web"


@dataclass(frozen=True, slots=True)
class PlateSpec:
    grade: str
    thickness: Geo


@dataclass(frozen=True, slots=True)
class AngleSpec:
    shape: str            # "L4x3_1_2x3_8"
    grade: str
    outstanding: str      # which leg lies on the support (or carries the seat): "long" | "short"


@dataclass(frozen=True, slots=True)
class TeeSpec:
    shape: str            # "WT9x25"
    parent: str           # "W18x50"
    grade: str


@dataclass(frozen=True, slots=True)
class Bolts:
    group: str            # "bolt_group.120"
    size: str             # "3_4"
    threads: str          # "included" | "excluded"
    joint: str            # "snug" | "pretensioned" | "slip_critical"
    surface: str | None   # "class_a" | "class_b", slip-critical only
    fillers: str          # "none" | "one" | "two"


@dataclass(frozen=True, slots=True)
class Weld:
    electrode: str        # "electrode.E70"
    size: Geo
    sides: int | None     # fillets per joint line, 1 or 2; None where the kind's geometry fixes the lines


@dataclass(frozen=True, slots=True)
class Cope:
    flanges: str          # "top" | "both"
    depth: Geo            # dc, or the top cope's dct when both flanges are coped
    length: Geo           # c, the same at both flanges
    bottom: Geo | None   # dcb when both flanges are coped (None: equal to depth)


@dataclass(frozen=True)
class Conn:
    """One connection. `attrs` maps an attribute key to its parsed value: a Geo, an int
    count, a word, or one of the dataclasses above."""

    name: str
    kind: str
    basis: str
    attrs: Mapping[str, object]
    span: Span

    def get(self, key: str) -> object:
        """The attribute, or what its absence means (ABSENT), or None: the feature is absent."""
        return self.attrs.get(key, ABSENT.get(key))


ABSENT: Mapping[str, object] = {
    "columns": 1,                   # one column of bolts
    "form": "conventional",         # a conventional single plate (Manual Part 10)
    "pair": "single",               # one concentrated force, not a pair on opposite flanges (J10.5)
    "holes": MappingProxyType({}),  # every ply has standard holes (Table J3.3)
    "weathering": "no",             # not unpainted weathering steel (J3.6(a)): no grade the registry holds is one
    "deformation": "considered",    # deformation at the hole a design consideration: J3.11a's lower coefficients
}
"""What an optional line's absence means: the feature is absent, or the reading that gives
the lower strength. An absence that would raise a strength is not here: that line is
required where a check reads it."""

WELD_SIDES = ("shear_tab", "shear_end_plate", "weld_bracket", "stiffened_seat")
"""Kinds whose `weld` line gives the fillets per joint line the strength reads."""

SET_BACK = ("shear_tab", "double_angle", "single_angle", "shear_tee")
"""Kinds whose coped beam stands off the support by its setback, the cope's moment arm
being c + setback (Manual Part 9). A seat's bearing length is its width less the setback,
so seated and stiffened_seat require it too; an end plate's beam is welded to the plate."""


Say = Callable[[str], None]
Parser = Callable[[str, str, tuple[Arg, ...], Design, Registry, Say], object]

HOLE_TYPES = ("std", "ovs", "ssl", "lsl", "ssl_parallel", "lsl_parallel")
JOINTS = ("snug", "pretensioned", "slip_critical")
SHAPE_GROUP = "aisc_shapes_v16"


def _reporter(problems: list[str], span: Span, what: str) -> Say:
    return lambda message: problems.append(f"{span.path}:{span.line}:{span.col}: {what}: {message}")


def _word_of(arg: Arg | None) -> str | None:
    return arg.parts[0] if isinstance(arg, Ref) and len(arg.parts) == 1 else None


def _id_of(arg: Arg | None) -> str | None:
    return ".".join(arg.parts) if isinstance(arg, Ref) else None


def _geo(conn: str, field: str, arg: Arg | None, design: Design, say: Say) -> Geo | None:
    """A positive length: Fixed, ParamRef or a signed Bound (-> Input "<conn>.<field>")."""
    if isinstance(arg, Fixed) and arg.quantity.dim == LENGTH and arg.quantity.value.lo > 0:
        return arg
    if isinstance(arg, ParamRef):
        param = design.params.get(arg.name)
        if param is not None and param.range.dim == LENGTH and param.range.value.lo > 0:
            return arg
        say(f"param {arg.name} is not a declared positive length")
        return None
    if isinstance(arg, Bound):
        if arg.range.dim != LENGTH or arg.range.value.lo <= 0:
            say("needs a positive length range")
            return None
        return Input(f"{conn}.{field}", arg.range, arg.signature, arg.kind, arg.span, arg.mean)
    say("needs a positive length, a signed bound `in [lo, hi] signed ... source ...`, or `param NAME`")
    return None


def _shape(arg: Arg | None, prefix: str, registry: Registry, say: Say) -> str | None:
    shape = _word_of(arg)
    prop = "t" if prefix == "L" else "d"
    if shape is None or not shape.startswith(prefix) or f"{SHAPE_GROUP}.{shape}.{prop}" not in registry.constants:
        say(registry.unknown(shape or str(arg), f"{prefix} shape", _shapes(prefix, prop, registry)))
        return None
    return shape


def _shapes(prefix: str, prop: str, registry: Registry) -> set[str]:
    """The shape table's designations that start with `prefix` and state `prop`."""
    out = set()
    for key in registry.constants:
        group, _, rest = key.partition(".")
        shape, _, stated = rest.partition(".")
        if group == SHAPE_GROUP and stated == prop and shape.startswith(prefix):
            out.add(shape)
    return out


THREAD_MARKS: Mapping[str, str] = {"N": "included", "X": "excluded"}
"""AISC's bolt suffixes, as in A325-N and A490-X (Table J3.2's columns): the threads are
included in (N) or excluded from (X) the shear planes."""


def _grade(arg: Arg | None, registry: Registry, say: Say, family: str) -> str | None:
    """The registry id the line names, a common name (A325, A992, "A572 Gr 50") read as its id."""
    named = arg.value if isinstance(arg, Text) else _id_of(arg) or ""
    grade = registry.canonical(named)
    try:
        material = registry.material(grade)
    except OutsideMakeableSet as e:
        say(_threads_note(named, registry) or str(e))
        return None
    if material.family != family:
        say(f"{grade} is a {material.family} material, not {family}")
        return None
    return grade


def _threads_note(named: str, registry: Registry) -> str | None:
    """For A325N or A325_N: what AISC's suffix means and how a `bolts` line says it."""
    stem, mark = named[:-1].rstrip("_"), named[-1:].upper()
    group = registry.materials.get(registry.canonical(stem))
    if mark not in THREAD_MARKS or group is None or group.family != "bolt":
        return None
    return (f"{named} is not a registry material: AISC's suffix -N means threads included in the shear planes and "
            f"-X threads excluded, which a bolts line states apart from the group: `bolts {group.id} diameter "
            f"<length> threads {THREAD_MARKS[mark]}`")


def _keywords(args: tuple[Arg, ...], start: int, say: Say) -> dict[str, Arg] | None:
    """`word value word value ...` from args[start:]."""
    rest = args[start:]
    if len(rest) % 2:
        say("reads as `<keyword> <value>` pairs after its first argument")
        return None
    out: dict[str, Arg] = {}
    for word, value in zip(rest[::2], rest[1::2]):
        w = _word_of(word)
        if w is None or w in out:
            say(f"expected a keyword, found {word}")
            return None
        out[w] = value
    return out


def _usage(key: str) -> str:
    return f"reads `{key} {FIELDS[key].form}`"


def p_word(*choices: str) -> Parser:
    def parse(conn, key, args, design, registry, say):
        word = _word_of(args[0]) if len(args) == 1 else None
        if word not in choices:
            say(_usage(key))
            return None
        return word
    return parse


def p_length(conn, key, args, design, registry, say):
    if len(args) != 1:
        say(_usage(key))
        return None
    return _geo(conn, key, args[0], design, say)


def p_count(conn, key, args, design, registry, say):
    n = args[0] if len(args) == 1 else None
    if not (isinstance(n, Fixed) and n.quantity.dim == DIMENSIONLESS and n.quantity.value.lo == n.quantity.value.hi
            and n.quantity.value.lo.denominator == 1 and n.quantity.value.lo >= 1):
        say(f"{_usage(key)}, a whole number at least 1 on a line of its own")
        return None
    return int(n.quantity.value.lo)


def p_member(face: bool) -> Parser:
    def parse(conn, key, args, design, registry, say):
        match tuple(args):
            case (shape_arg, side, word, grade_arg) if face and _word_of(side) in ("flange", "web") and _word_of(word) == "grade":
                which = _word_of(side)
            case (shape_arg, word, grade_arg) if not face and _word_of(word) == "grade":
                which = None
            case _:
                say(_usage(key))
                return None
        shape, grade = _shape(shape_arg, "W", registry, say), _grade(grade_arg, registry, say, "steel")
        return Member(shape, grade, which) if shape and grade else None
    return parse


def p_plate(conn, key, args, design, registry, say):
    kw = _keywords(args, 1, say) if args else None
    if kw is None or set(kw) != {"thickness"}:
        say(_usage(key))
        return None
    grade = _grade(args[0], registry, say, "steel")
    t = _geo(conn, f"{key}.thickness", kw["thickness"], design, say)
    if isinstance(t, Fixed) and not _stocked(t.quantity.value.lo, registry):
        say(f"{float(t.quantity.value.lo / INCH):g} in is not a stocked plate thickness (registry {STOCK_PLATE}*)")
        return None
    return PlateSpec(grade, t) if grade and t else None


def _stocked(thickness: Fraction, registry: Registry) -> bool:
    """A fixed plate thickness is makeable when the shop deck stocks it. A thickness left
    as a parameter or a toleranced bound is a nominal the fabricator orders from the
    same list; lowering cannot check a value it does not yet know."""
    return any(name.startswith(STOCK_PLATE) and c.value.lo == thickness for name, c in registry.constants.items())


def p_angle(conn, key, args, design, registry, say):
    kw = _keywords(args, 1, say) if args else None
    if kw is None or set(kw) != {"grade", "outstanding"} or _word_of(kw["outstanding"]) not in ("long", "short"):
        say(_usage(key))
        return None
    shape, grade = _shape(args[0], "L", registry, say), _grade(kw["grade"], registry, say, "steel")
    return AngleSpec(shape, grade, _word_of(kw["outstanding"])) if shape and grade else None


def tee_parent(shape: str) -> str | None:
    """WT9x25 -> W18x50, WT5x22_5 -> W10x45: a WT is half its parent W."""
    if not shape.startswith("WT") or "x" not in shape:
        return None
    depth, weight = shape[2:].split("x", 1)
    try:
        d, w = Fraction(depth.replace("_", ".")), Fraction(weight.replace("_", "."))
    except ValueError:
        return None
    text = lambda x: str(x.numerator) if x.denominator == 1 else str(float(x)).replace(".", "_")
    return f"W{text(2 * d)}x{text(2 * w)}"


def p_tee(conn, key, args, design, registry, say):
    kw = _keywords(args, 1, say) if args else None
    shape = _word_of(args[0]) if args else None
    parent = tee_parent(shape or "")
    if kw is None or set(kw) != {"grade"} or parent is None:
        say(_usage(key))
        return None
    if f"{SHAPE_GROUP}.{parent}.d" not in registry.constants:
        say(f"{shape} is cut from {parent}, which is not in the shape table")
        return None
    grade = _grade(kw["grade"], registry, say, "steel")
    return TeeSpec(shape, parent, grade) if grade else None


def p_bolts(conn, key, args, design, registry, say):
    from ...registry.steel import BOLT_SIZES, size_id
    kw = _keywords(args, 1, say) if args else None
    if kw is None or not {"diameter", "threads"} <= set(kw) <= {"diameter", "threads", "joint", "surface", "fillers"}:
        say(_usage(key))
        return None
    group = _grade(args[0], registry, say, family="bolt")
    d = kw["diameter"]
    size = None
    if isinstance(d, Fixed) and d.quantity.dim == LENGTH:
        from ...units import CUSTOMARY
        inches = d.quantity.value.lo / CUSTOMARY["inch"][0]
        size = next((size_id(s) for s in BOLT_SIZES if _inch(s) == inches and d.quantity.value.lo == d.quantity.value.hi), None)
    if size is None:
        say(f"diameter is one of the RCSC 2025 Table 5.2 sizes: {', '.join(s + ' inch' for s in BOLT_SIZES)}")
    threads, joint = _word_of(kw["threads"]), _word_of(kw.get("joint", Ref(("snug",))))
    surface, fillers = _word_of(kw["surface"]) if "surface" in kw else None, _word_of(kw.get("fillers", Ref(("none",))))
    ok = group is not None and size is not None
    if threads not in ("included", "excluded"):
        say("threads is included or excluded (from the shear planes)")
        ok = False
    if joint not in JOINTS:
        say(f"joint is one of {', '.join(JOINTS)}")
        ok = False
    if surface not in (None, "class_a", "class_b") or (joint == "slip_critical") != (surface is not None):
        say("a slip-critical joint names its faying surface class_a or class_b, and only a slip-critical joint does")
        ok = False
    if fillers not in ("none", "one", "two"):
        say("fillers is none, one or two")
        ok = False
    return Bolts(group, size, threads, joint, surface, fillers) if ok else None


def _inch(size: str) -> Fraction:
    whole, _, frac = size.partition("-")
    return Fraction(whole) + (Fraction(frac) if frac else 0)


def p_holes(plies: tuple[str, ...]) -> Parser:
    def parse(conn, key, args, design, registry, say):
        words = [_word_of(a) for a in args]
        if not words or len(words) % 2 or any(w is None for w in words):
            say(f"reads `{key} <ply> <hole type> ...` with plies {', '.join(plies)}")
            return None
        out = dict(zip(words[::2], words[1::2]))
        if not set(out) <= set(plies) or len(out) * 2 != len(words) or any(t not in HOLE_TYPES for t in out.values()):
            say(f"names plies among {', '.join(plies)}, each once, each with one of {', '.join(HOLE_TYPES)}; "
                "a ply it does not name has standard holes")
            return None
        return out
    return parse


def p_weld(conn, key, args, design, registry, say):
    kw = _keywords(args, 1, say) if args else None
    if kw is None or not {"size"} <= set(kw) <= {"size", "sides"}:
        say(_usage(key))
        return None
    electrode = _grade(args[0], registry, say, family="electrode")
    size = _geo(conn, f"{key}.size", kw["size"], design, say)
    sides = kw.get("sides")
    n = sides.quantity.value.lo if isinstance(sides, Fixed) and sides.quantity.dim == DIMENSIONLESS else None
    if sides is not None and n not in (1, 2):
        say("sides is 1 or 2")
        return None
    return Weld(electrode, size, None if n is None else int(n)) if electrode and size else None


def p_cope(conn, key, args, design, registry, say):
    kw = _keywords(args, 1, say) if args else None
    flanges = _word_of(args[0]) if args else None
    allowed = {"depth", "length"} | ({"bottom_depth"} if flanges == "both" else set())
    if kw is None or not {"depth", "length"} <= set(kw) <= allowed or flanges not in ("top", "both"):
        say(f"{_usage(key)}; bottom_depth goes with both")
        return None
    depth = _geo(conn, "cope.depth", kw["depth"], design, say)
    length = _geo(conn, "cope.length", kw["length"], design, say)
    bottom = _geo(conn, "cope.bottom_depth", kw["bottom_depth"], design, say) if "bottom_depth" in kw else None
    if "bottom_depth" in kw and bottom is None:
        return None
    return Cope(flanges, depth, length, bottom) if depth and length else None


# --- Kinds ----------------------------------------------------------------------------------

_WORDS: Mapping[str, tuple[str, ...]] = {
    "basis": ("lrfd", "asd"),
    "deformation": ("considered", "not_considered"),
    "form": ("conventional", "extended"),
    "support_side": ("bolted", "welded"),
    "location": ("interior", "end"),
    "end_twist": ("restrained", "free"),
    "force_kind": ("compressive", "tensile"),
    "pair": ("single", "double"),
    "flange_restrained": ("yes", "no"),
    "moment_at_force": ("below_yield", "at_yield"),
    "weathering": ("no", "yes"),
}
"""The lines that name one word: line -> the words it takes."""

_LENGTHS: Mapping[str, str] = {
    "pitch": "spacing of bolt rows (s)",
    "gauge": "spacing of bolt columns (g)",
    "edge_vertical": "vertical edge distance of the end rows (Lev)",
    "plate_edge": "horizontal edge distance on the connecting element (Leh)",
    "bolt_line": "distance a to the bolt line (Manual Part 10)",
    "beam_edge": "horizontal edge distance on the beam web, as detailed; strength checks take it less the 1/4 in "
                 "underrun (Leh, Manual Part 10)",
    "top": "beam's top to the top bolt row",
    "setback": "gap from the support face to the beam end, as detailed; a seat's strength checks add the 1/4 in "
               "underrun",
    "eccentricity": "load's distance from the bolt group's or weld's centroid (e)",
    "beam_gauge": "gauge of the bolts through the beam web (g)",
    "support_gauge": "gauge of the bolts through the support (g)",
    "plate_width": "an end plate's width",
    "seat_length": "a seat angle's length along the beam's width",
    "bearing_length": "length of bearing (lb, J10)",
    "distance": "from the member end to a concentrated force (J10)",
    "unbraced_length": "J10.4's laterally unbraced length (Lb)",
    "stiffener_width": "width of a seat stiffener (W, Manual Table 10-8)",
    "stiffener_length": "length of a seat stiffener and its welds (l)",
    "weld_length": "length of a bracket's weld line (L)",
    "tee_gauge": "gauge across a hanger tee's flange (g)",
    "weld_return": "a bracket weld's returns (kl): a C-shaped weld around a plate lapped on the support face",
    "free_edge": "a shaped bracket's free edge, projected (b)",
}
"""The lines that give one length: line -> its meaning, with the symbol docs/steel_glossary.md
maps it to."""

READINGS: Mapping[str, Mapping[str, str]] = {
    "support_gauge": {
        "double_angle": "between the two bolt lines, one in each angle's outstanding leg: twice each leg's gauge "
                        "from its heel, plus the beam web's thickness",
        "single_angle": "from the angle's heel, at the face of the beam web, to the bolt line in its outstanding leg",
        "shear_tee": "between the two bolt lines across the tee flange, one each side of the stem",
        "shear_end_plate": "between the two bolt lines across the end plate, one each side of the beam web",
        "seated": "between the two bolt lines across the seat angle's vertical leg",
    },
    "beam_gauge": {
        "double_angle": "from the angles' heel, the back of their outstanding legs, to the bolt line in the legs on "
                        "the beam web; the toe's edge distance is that leg less this gauge",
        "single_angle": "from the angle's heel, the back of its outstanding leg, to the bolt line in the leg on the "
                        "beam web; the toe's edge distance is that leg less this gauge",
    },
    "bolt_line": {
        "shear_tab": "from the weld line at the support face; with more than one column, to the column nearest the "
                     "support",
        "shear_tee": "measured along the stem from the back of the tee flange, at the support face",
    },
}
"""The lines each kind measures its own way: line -> kind -> where it is measured from or
between, which follows the line's meaning in the kind's grammar. Every kind that takes the
line has its reading (tests/test_teach.py)."""

_COMMON: dict[str, Parser] = {
    "beam": p_member(False),
    "support": p_member(True),
    "member": p_member(False),
    "plate": p_plate,
    "stiffener": p_plate,
    "angles": p_angle,
    "angle": p_angle,
    "top_angle": p_angle,
    "tee": p_tee,
    "bolts": p_bolts,
    "weld": p_weld,
    "support_weld": p_weld,
    "cope": p_cope,
    "rows": p_count,
    "columns": p_count,
    **{name: p_word(*words) for name, words in _WORDS.items()},
    **{name: p_length for name in _LENGTHS},
}

_ANGLE = "<L shape> grade <steel grade> outstanding long|short"
_WELD = "<electrode> size <length> [sides 1|2]"

FIELDS: Mapping[str, Field] = {f.name: f for f in (
    Field("basis", "|".join(_WORDS["basis"]), "", (),
          "the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega)"),
    Field("beam", "<W shape> grade <steel grade>", "", ("W", "steel."), "the supported beam, a W shape from the shape table"),
    Field("support", "<W shape> flange|web grade <steel grade>", "", ("W", "steel."),
          "the supporting member and the face the connection meets: a column flange, or a column or girder web"),
    Field("member", "<W shape> grade <steel grade>", "", ("W", "steel."), "the member the concentrated force acts on"),
    Field("plate", "<steel grade> thickness <length>", "length", ("steel.",),
          "the connecting plate (a shear tab, end plate, seat plate or bracket plate); a fixed thickness is a stocked one"),
    Field("stiffener", "<steel grade> thickness <length>", "length", ("steel.",), "a stiffened seat's stiffener plate"),
    Field("angles", _ANGLE, "", ("L", "steel."), "the pair of connection angles; outstanding names the leg on the support"),
    Field("angle", _ANGLE, "", ("L", "steel."),
          "the single angle, or a seat's angle; outstanding names the leg on the support, or the seat's leg under the beam"),
    Field("top_angle", _ANGLE, "", ("L", "steel."), "a seat's top angle, which holds the beam's top flange in place"),
    Field("tee", "<WT shape> grade <steel grade>", "", ("WT", "steel."),
          "the tee, cut from a W shape in the shape table (WT9x25 from W18x50)"),
    Field("bolts", "<bolt group> diameter <length> threads included|excluded [joint snug|pretensioned|slip_critical] "
                   "[surface class_a|class_b] [fillers none|one|two]", "length", ("bolt_group.",),
          "the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, "
          "threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the "
          "installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated)"),
    Field("weld", _WELD, "length", ("electrode.",),
          f"the fillet weld: electrode, leg size, and fillets at each joint line, which {', '.join(WELD_SIDES)} state"),
    Field("support_weld", _WELD, "length", ("electrode.",), "the weld to the support on a welded support side"),
    Field("cope", "top|both depth <length> length <length> [bottom_depth <length>]", "length", (),
          "a cope at the beam's top flange or both flanges: the (top) cope's depth, its length, and with both a "
          "bottom depth where it differs; a coped beam states its setback"),
    Field("rows", "<n>", "count", (), "bolt rows, a whole number"),
    Field("columns", "<n>", "count", (), "bolt columns; one unless stated"),
    Field("deformation", "|".join(_WORDS["deformation"]), "", (),
          "whether deformation at the bolt holes at service load is a design consideration (Section J3.11a); "
          "considered unless stated"),
    Field("form", "|".join(_WORDS["form"]), "", (),
          "a single plate's configuration (Manual Part 10); conventional unless stated"),
    Field("support_side", "|".join(_WORDS["support_side"]), "", (),
          "how the angles, tee or seat meet the support: bolted (with support_gauge) or welded (with support_weld)"),
    Field("location", "|".join(_WORDS["location"]), "", (),
          "where the force acts: away from the member's ends, or near one (with distance)"),
    Field("end_twist", "|".join(_WORDS["end_twist"]), "", (),
          "whether the member end near the force is framed or otherwise restrained against twisting about its "
          "longitudinal axis, or free; a free end needs a pair of full-depth stiffeners (Section J10.7)"),
    Field("force_kind", "|".join(_WORDS["force_kind"]), "", (), "the sense of the concentrated force"),
    Field("pair", "|".join(_WORDS["pair"]), "", (),
          "one force, or a pair of compressive forces on opposite flanges at one section (Section J10.5); single "
          "unless stated"),
    Field("flange_restrained", "|".join(_WORDS["flange_restrained"]), "", (),
          "whether the loaded flange is restrained against rotation, which web sidesway buckling (Section J10.4) reads"),
    Field("moment_at_force", "|".join(_WORDS["moment_at_force"]), "", (),
          "whether the member's moment at the force is below or at yield, which sets J10.4's Cr"),
    Field("weathering", "|".join(_WORDS["weathering"]), "", (),
          "whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no "
          "unless stated"),
    *(Field(name, "<length>", "length", (), meaning) for name, meaning in _LENGTHS.items()),
)}
"""Every attribute line but `holes`, whose plies are the kind's: its form, which the line's
usage error prints, and its meaning. A <length> is a length, a signed bound or a param."""


def grammar(kind: str) -> Grammar:
    """The kind's lines, required and optional, as KIND_SPECS lists them, each line with
    the kind's own reading of it (READINGS)."""
    spec = KIND_SPECS[kind]
    holes = Field("holes", f"<ply> {'|'.join(HOLE_TYPES)} [<ply> <type> ...]", "", (),
                  f"hole types by ply (Table J3.3), plies {', '.join(spec.plies) or 'none'}; a ply it does not "
                  "name has standard holes")
    fields = {**FIELDS, "holes": holes,
              **{line: replace(FIELDS[line], meaning=f"{FIELDS[line].meaning}, {by_kind[kind]}")
                 for line, by_kind in READINGS.items() if kind in by_kind}}
    return Grammar(tuple(fields[n] for n in spec.required), tuple(fields[n] for n in spec.optional), "<conn>",
                   spec.loads)


@dataclass(frozen=True)
class KindSpec:
    required: tuple[str, ...]
    optional: tuple[str, ...]
    plies: tuple[str, ...]          # names the holes line uses
    loads: tuple[str, ...]          # load fields; the first is the one every builder needs


KIND_SPECS: Mapping[str, KindSpec] = {
    "shear_tab": KindSpec(
        ("basis", "beam", "support", "plate", "bolts", "rows", "pitch", "edge_vertical", "plate_edge",
         "bolt_line", "beam_edge", "top", "weld"),
        ("holes", "cope", "eccentricity", "setback", "form", "columns", "gauge", "deformation", "weathering"),
        ("plate", "beam"), ("shear", "axial")),
    "double_angle": KindSpec(
        ("basis", "beam", "support", "angles", "bolts", "rows", "pitch", "edge_vertical", "beam_edge", "top",
         "beam_gauge", "support_side"),
        ("holes", "support_gauge", "support_weld", "cope", "setback", "deformation", "weathering"),
        ("angles", "beam", "support"), ("shear", "axial")),
    "single_angle": KindSpec(
        ("basis", "beam", "support", "angle", "bolts", "rows", "pitch", "edge_vertical", "beam_edge", "top",
         "beam_gauge", "support_side"),
        ("holes", "support_gauge", "support_weld", "cope", "setback", "deformation", "weathering"),
        ("angle", "beam", "support"), ("shear", "axial")),
    "shear_tee": KindSpec(
        ("basis", "beam", "support", "tee", "bolts", "rows", "pitch", "edge_vertical", "bolt_line",
         "beam_edge", "top", "support_side"),
        ("holes", "support_gauge", "support_weld", "cope", "setback", "eccentricity", "deformation", "weathering"),
        ("stem", "flange", "beam", "support"), ("shear", "axial")),
    "shear_end_plate": KindSpec(
        ("basis", "beam", "support", "plate", "plate_width", "bolts", "rows", "pitch", "edge_vertical",
         "support_gauge", "weld"),
        ("holes", "cope", "setback", "deformation", "weathering"),
        ("plate", "support"), ("shear", "axial")),
    "seated": KindSpec(
        ("basis", "beam", "support", "angle", "seat_length", "support_side", "top_angle"),
        ("bolts", "holes", "rows", "pitch", "edge_vertical", "support_gauge", "setback", "support_weld",
         "deformation", "weathering"),
        ("angle", "support"), ("shear", "axial")),
    "stiffened_seat": KindSpec(
        ("basis", "beam", "support", "plate", "stiffener", "stiffener_width", "stiffener_length", "weld",
         "top_angle"),
        ("setback",),
        (), ("shear", "axial")),
    "flange_force": KindSpec(
        ("basis", "member", "bearing_length", "location", "force_kind"),
        ("distance", "end_twist", "pair", "flange_restrained", "unbraced_length", "moment_at_force"),
        (), ("force", "panel_shear", "axial")),
    "bolt_bracket": KindSpec(
        ("basis", "plate", "support", "bolts", "rows", "columns", "pitch", "gauge", "eccentricity",
         "edge_vertical", "plate_edge"),
        ("holes", "deformation", "weathering", "free_edge"),
        ("plate", "support"), ("shear",)),
    "weld_bracket": KindSpec(
        ("basis", "plate", "support", "weld", "weld_length", "eccentricity"),
        ("weld_return", "free_edge"),
        (), ("shear",)),
    "hanger": KindSpec(
        ("basis", "tee", "support", "bolts", "rows", "pitch", "tee_gauge", "edge_vertical"),
        ("holes", "weathering"),
        ("flange", "support"), ("tension", "shear")),
}
"""Each kind's attribute lines. Every kind needs `basis`; the plies are what `holes`
names; the first load field is the one every requirement on the kind is checked under."""


def lower_conn(component: Component, design: Design, registry: Registry) -> Conn:
    spec = KIND_SPECS[component.kind]
    problems: list[str] = []
    name = component.name
    attrs: dict[str, object] = {}
    allowed = set(spec.required) | set(spec.optional)
    for attr in component.attrs:
        say = _reporter(problems, attr.span, f"{name}.{attr.key}")
        if attr.key == "holes" and spec.plies:
            parser: Parser | None = p_holes(spec.plies)
        else:
            parser = _COMMON.get(attr.key) if attr.key in allowed else None
        if parser is None or (attr.key == "holes" and "holes" not in allowed):
            say(f"unknown attribute; a {component.kind} takes {', '.join(sorted(allowed))}")
            continue
        if attr.key in attrs:
            say("is given twice")
            continue
        value = parser(name, attr.key, attr.args, design, registry, say)
        if value is not None:
            attrs[attr.key] = value
    here = _reporter(problems, component.span, name)
    given = {attr.key for attr in component.attrs}
    missing = [k for k in spec.required if k not in given]
    if missing:
        here(f"a {component.kind} needs {', '.join(missing)}: "
             + "; ".join(f"`{k} {FIELDS[k].form}`" for k in missing))
    _check_kind(component.kind, attrs, here)
    _check_references(name, component.kind, design, problems)
    if problems:
        raise ComponentError(tuple(problems))
    return Conn(name, component.kind, str(attrs["basis"]), attrs, component.span)


def _check_kind(kind: str, attrs: Mapping[str, object], say: Say) -> None:
    """The combinations a kind's lines must agree on."""
    side = attrs.get("support_side")
    if side == "bolted" and "support_gauge" not in attrs:
        say(f"a bolted support side names support_gauge, {READINGS['support_gauge'][kind]}")
    if side == "bolted" and kind == "seated" and not {"bolts", "rows", "pitch", "edge_vertical"} <= set(attrs):
        say("a bolted seat names its bolts, rows, pitch and edge_vertical")
    if side == "welded" and "support_weld" not in attrs:
        say("a welded support side names its support_weld")
    if side == "bolted" and "support_weld" in attrs:
        say("a bolted support side takes no support_weld")
    if side == "welded" and kind == "seated" and "bolts" in attrs:
        say("a welded seat takes no bolts")
    if kind == "shear_tab" and attrs.get("columns", 1) > 1 and "gauge" not in attrs:
        say("a shear tab with more than one bolt column names its gauge")
    if kind in ("shear_tab", "double_angle", "single_angle", "shear_tee") and isinstance(attrs.get("rows"), int) and attrs["rows"] < 2:
        say("a beam-side bolt group has at least two rows, so it can resist the eccentricity")
    if kind in WELD_SIDES and isinstance(attrs.get("weld"), Weld) and attrs["weld"].sides is None:
        say(f"a {kind}'s weld states its sides, 1 or 2: the fillets at each joint line, which its weld strength reads")
    if (kind in SET_BACK and "cope" in attrs or kind in ("seated", "stiffened_seat")) and "setback" not in attrs:
        say(f"a {'coped beam' if kind in SET_BACK else kind.replace('_', ' ')} states its setback from the support, "
            "which its cope's moment arm or its bearing length reads")
    if kind == "weld_bracket" and "weld_return" in attrs and isinstance(attrs.get("weld"), Weld) and attrs["weld"].sides != 1:
        say("a weld_return makes a C-shaped weld around a plate lapped on the support face: one fillet, `sides 1`")
    if kind == "bolt_bracket" and isinstance(attrs.get("rows"), int) and attrs["rows"] * attrs.get("columns", 1) < 2:
        say("an eccentric bolt group has at least two bolts")
    if kind == "hanger" and isinstance(attrs.get("support"), Member) and attrs["support"].face != "flange":
        say("a hanger hangs from the support's flange (the tee's bolts pass through it and it bends about the web)")
    if kind == "flange_force" and attrs.get("location") == "end" and "distance" not in attrs:
        say("a force at the member end names its distance from the end")
    if kind == "flange_force" and attrs.get("location") == "end" and "end_twist" not in attrs:
        say("a force at the member end says whether that end is restrained against twisting about its axis "
            "(end_twist restrained|free): a free end needs a pair of full-depth stiffeners (J10.7)")
    if kind == "flange_force" and attrs.get("location") == "interior" and "distance" in attrs:
        say("an interior force takes no distance; a force near the end is at location end")
    if kind == "flange_force" and attrs.get("location") == "interior" and "end_twist" in attrs:
        say("an interior force takes no end_twist; a force near the end is at location end")
    if kind == "flange_force" and attrs.get("pair") == "double" and attrs.get("force_kind") == "tensile":
        say("a double (pair) force is compressive; J10.5 has no tensile pair")
    if (kind == "flange_force" and attrs.get("force_kind") == "compressive" and attrs.get("pair", "single") == "single"
            and not {"flange_restrained", "unbraced_length", "moment_at_force"} <= set(attrs)):
        say("a single compressive force names flange_restrained, unbraced_length and moment_at_force, which web sidesway "
            "buckling (J10.4) reads")
    bolts = attrs.get("bolts")
    if isinstance(bolts, Bolts):
        if bolts.joint == "slip_critical" and bolts.group not in ("bolt_group.120", "bolt_group.150"):
            say("a slip-critical joint uses Group 120 or 150 bolts, whose minimum pretension Table J3.1 gives")
        if bolts.joint != "snug" and bolts.group == "bolt_group.A307":
            say("A307 bolts are installed snug-tight; they have no specified pretension")


def _dim(value: Input | ParamRef, design: Design) -> Dim:
    return value.range.dim if isinstance(value, Input) else design.params[value.name].range.dim


def _check_references(conn: str, kind: str, design: Design, problems: list[str]) -> None:
    from .vocab import QOIS
    fields = KIND_SPECS[kind].loads
    for case in design.loads.values():
        say = _reporter(problems, case.span, f"load {case.name}")
        seen: set[str] = set()
        for entry in (e for e in case.entries if e.target[0] == conn):
            if len(entry.target) != 1:
                say(f"{'.'.join(entry.target)}: a connection load acts on the connection, as in `on {conn} {fields[0]} ...`")
            elif entry.field not in fields:
                say(f"{conn}: a {kind} takes load fields {', '.join(fields)}, not {entry.field}")
            elif entry.field in seen:
                say(f"{conn}: {entry.field} is given twice")
            elif _dim(entry.value, design) != FORCE:
                say(f"{conn}: {entry.field} needs a force range")
            elif _lo(entry.value, design) < 0 and entry.field != "axial":
                say(f"{conn}: {entry.field} is a magnitude, not negative; its sense is fixed by the connection")
            seen.add(entry.field)
    for claim in design.claims:
        if claim.qoi.path[0] != conn:
            continue
        say = _reporter(problems, claim.span, f"claim {claim.name}")
        if len(claim.qoi.path) != 1:
            say(f"a connection claim names the connection, as in {conn}.bolts")
        elif claim.qoi.name not in QOIS:
            say(f"unknown connection quantity '{claim.qoi.name}'; known: {', '.join(sorted(QOIS))}")
        elif claim.bound.dim != DIMENSIONLESS:
            say(f"{claim.qoi.name} is a utilisation, bounded by a dimensionless number")
    for claim in design.probability_claims:
        path = claim.event.qoi.path if isinstance(claim.event, Exceeds) else claim.event.subject
        if path[0] == conn:
            _reporter(problems, claim.span, f"claim {claim.name}")("the steel deck states no probability claims")
    for tests in design.tests.values():
        if tests.subject[0] == conn:
            _reporter(problems, tests.span, f"tests {tests.name}")("the steel deck reads no tests records")
    for waiver in design.waivers:
        if waiver.subject[0] == conn and len(waiver.subject) != 1:
            _reporter(problems, waiver.span, "waiver")(f"a connection's requirements are on {conn} itself")


def _lo(value: Input | ParamRef, design: Design) -> Fraction:
    return value.range.value.lo if isinstance(value, Input) else design.params[value.name].range.value.lo
