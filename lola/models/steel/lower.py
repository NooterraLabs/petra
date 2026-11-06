"""Lowering for the steel-connection deck: attribute lines -> a typed Conn. Trusted.

Every connection kind reads the same attribute grammar, one attribute per line:

    basis lrfd|asd
    beam <W shape> grade <material>
    support <W shape> flange|web grade <material>
    member <W shape> grade <material>                   (flange_force)
    plate <material> thickness <len>                    (shear_tab, shear_end_plate, stiffened_seat)
    stiffener <material> thickness <len>                (stiffened_seat)
    angles <L shape> grade <material> outstanding long|short     (double_angle, single angle: angle)
    angle  <L shape> grade <material> outstanding long|short
    tee <WT shape> grade <material>                     (shear_tee, hanger)
    bolts <group> diameter <len> threads included|excluded [joint snug|pretensioned|slip_critical]
          [surface class_a|class_b] [fillers none|one|two]
    holes <ply> std|ovs|ssl|lsl|ssl_parallel|lsl_parallel [<ply> <type> ...]   (unnamed plies: std)
    weld <electrode> size <len> [sides 1|2]
    support_side bolted|welded        beam_side bolted|welded
    support_weld <electrode> size <len>    beam_weld <electrode> size <len>
    cope top|both depth <len> length <len> [bottom_depth <len>]
    weld_return <len>       (weld_bracket: returns at both ends of the weld, a C-shape on a lapped plate)
    free_edge <len>         (bolt_bracket, weld_bracket: a shaped plate's sloped free edge, projected)
    rows <n>   columns <n>   support_rows <n>
    deformation considered|not_considered
    form conventional|extended
    <length field> <len>              (pitch, gauge, edge_vertical, ... per kind)

A <len> is a length (Fixed), a signed bound `in [lo, hi] signed "..." source "..."`
(an ir.Input named "<conn>.<field>", which the pipeline's premise book finds in the
typed model), or `param NAME`. A count is a whole number on a line of its own. Shapes are
designations: W18x50, L4x3_1_2x3_8 (L4x3-1/2x3/8), WT9x25 (cut from W18x50).

Load fields per kind: LOAD_FIELDS. Claims name `<conn>.<qoi>`, a mode's short name
(QOIS in vocab.py), bounded by a dimensionless utilisation.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Mapping, Union

from ...ir import Arg, Bound, Component, Design, Exceeds, Fixed, Input, ParamRef, Ref, Span
from ...registry import OutsideMakeableSet, Registry
from ...registry.steel import INCH, STOCK_PLATE
from ...units import DIMENSIONLESS, FORCE, LENGTH, Dim
from ..base import ComponentError

Geo = Union[Fixed, ParamRef, Input]
"""A design length: a fixed value, a scope parameter, or a signed toleranced bound."""


@dataclass(frozen=True, slots=True)
class Member:
    shape: str            # "W18x50"
    grade: str            # "steel.A992"
    face: str | None = None   # a support's connected face: "flange" | "web"


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
    sides: int            # fillets per joint line: 1 or 2


@dataclass(frozen=True, slots=True)
class Cope:
    flanges: str          # "top" | "both"
    depth: Geo            # dc, or the top cope's dct when both flanges are coped
    length: Geo           # c, the same at both flanges
    bottom: Geo | None = None   # dcb when both flanges are coped (None: equal to depth)


@dataclass(frozen=True)
class Conn:
    """One connection. `attrs` maps an attribute key to its parsed value: a Geo, an int
    count, a word, or one of the dataclasses above."""

    name: str
    kind: str
    basis: str
    attrs: Mapping[str, object]
    span: Span

    def get(self, key: str, default: object = None) -> object:
        return self.attrs.get(key, default)


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


def _geo(conn: str, field: str, arg: Arg | None, design: Design, say: Say, dim: Dim = LENGTH) -> Geo | None:
    """A positive length: Fixed, ParamRef or a signed Bound (-> Input "<conn>.<field>")."""
    if isinstance(arg, Fixed) and arg.quantity.dim == dim and arg.quantity.value.lo > 0:
        return arg
    if isinstance(arg, ParamRef):
        param = design.params.get(arg.name)
        if param is not None and param.range.dim == dim and param.range.value.lo > 0:
            return arg
        say(f"param {arg.name} is not a declared positive {'length' if dim == LENGTH else 'quantity'}")
        return None
    if isinstance(arg, Bound):
        if arg.range.dim != dim or arg.range.value.lo <= 0:
            say("needs a positive length range")
            return None
        return Input(f"{conn}.{field}", arg.range, arg.signature, arg.kind, arg.span, arg.mean)
    say("needs a positive length, a signed bound `in [lo, hi] signed ... source ...`, or `param NAME`")
    return None


def _shape(arg: Arg | None, prefix: str, registry: Registry, say: Say) -> str | None:
    shape = _word_of(arg)
    if shape is None or not shape.startswith(prefix) or f"{SHAPE_GROUP}.{shape}.{'t' if prefix == 'L' else 'd'}" not in registry.constants:
        say(f"{shape or arg} is not a {prefix} shape in the shape table")
        return None
    return shape


def _grade(arg: Arg | None, registry: Registry, say: Say, family: str = "steel") -> str | None:
    grade = _id_of(arg)
    try:
        material = registry.material(grade or "")
    except OutsideMakeableSet as e:
        say(str(e))
        return None
    if material.family != family:
        say(f"{grade} is a {material.family} material, not {family}")
        return None
    return grade


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


def p_word(*choices: str) -> Parser:
    def parse(conn, key, args, design, registry, say):
        word = _word_of(args[0]) if len(args) == 1 else None
        if word not in choices:
            say(f"reads `{key} {'|'.join(choices)}`")
            return None
        return word
    return parse


def p_length(conn, key, args, design, registry, say):
    if len(args) != 1:
        say(f"reads `{key} <length>`")
        return None
    return _geo(conn, key, args[0], design, say)


def p_count(conn, key, args, design, registry, say):
    n = args[0] if len(args) == 1 else None
    if not (isinstance(n, Fixed) and n.quantity.dim == DIMENSIONLESS and n.quantity.value.lo == n.quantity.value.hi
            and n.quantity.value.lo.denominator == 1 and n.quantity.value.lo >= 1):
        say(f"reads `{key} <n>`, a whole number at least 1 on a line of its own")
        return None
    return int(n.quantity.value.lo)


def p_member(face: bool) -> Parser:
    def parse(conn, key, args, design, registry, say):
        if face:
            ok = len(args) == 4 and _word_of(args[1]) in ("flange", "web") and _word_of(args[2]) == "grade"
            shape_arg, grade_arg = args[0] if args else None, args[3] if len(args) == 4 else None
        else:
            ok = len(args) == 3 and _word_of(args[1]) == "grade"
            shape_arg, grade_arg = args[0] if args else None, args[2] if len(args) == 3 else None
        if not ok:
            say(f"reads `{key} <W shape> {'flange|web ' if face else ''}grade <material>`")
            return None
        shape, grade = _shape(shape_arg, "W", registry, say), _grade(grade_arg, registry, say)
        return Member(shape, grade, _word_of(args[1]) if face else None) if shape and grade else None
    return parse


def p_plate(conn, key, args, design, registry, say):
    kw = _keywords(args, 1, say) if args else None
    if kw is None or set(kw) != {"thickness"}:
        say(f"reads `{key} <material> thickness <len>`")
        return None
    grade = _grade(args[0], registry, say)
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
        say(f"reads `{key} <L shape> grade <material> outstanding long|short`")
        return None
    shape, grade = _shape(args[0], "L", registry, say), _grade(kw["grade"], registry, say)
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
        say(f"reads `{key} <WT shape> grade <material>`")
        return None
    if f"{SHAPE_GROUP}.{parent}.d" not in registry.constants:
        say(f"{shape} is cut from {parent}, which is not in the shape table")
        return None
    grade = _grade(kw["grade"], registry, say)
    return TeeSpec(shape, parent, grade) if grade else None


def p_bolts(conn, key, args, design, registry, say):
    from ...registry.steel import BOLT_SIZES, size_id
    kw = _keywords(args, 1, say) if args else None
    usage = (f"reads `{key} <bolt group> diameter <len> threads included|excluded [joint snug|pretensioned|"
             "slip_critical] [surface class_a|class_b] [fillers none|one|two]`")
    if kw is None or not {"diameter", "threads"} <= set(kw) <= {"diameter", "threads", "joint", "surface", "fillers"}:
        say(usage)
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
        say(f"reads `{key} <electrode> size <len> [sides 1|2]`")
        return None
    electrode = _grade(args[0], registry, say, family="electrode")
    size = _geo(conn, f"{key}.size", kw["size"], design, say)
    sides = kw.get("sides", Fixed(_dimensionless(2)))
    n = sides.quantity.value.lo if isinstance(sides, Fixed) and sides.quantity.dim == DIMENSIONLESS else None
    if n not in (1, 2):
        say("sides is 1 or 2")
        return None
    return Weld(electrode, size, int(n)) if electrode and size else None


def _dimensionless(n: int):
    from ...kernel import Interval
    from ...units import Quantity
    return Quantity(Interval(Fraction(n), Fraction(n)), DIMENSIONLESS)


def p_cope(conn, key, args, design, registry, say):
    kw = _keywords(args, 1, say) if args else None
    flanges = _word_of(args[0]) if args else None
    allowed = {"depth", "length"} | ({"bottom_depth"} if flanges == "both" else set())
    if kw is None or not {"depth", "length"} <= set(kw) <= allowed or flanges not in ("top", "both"):
        say(f"reads `{key} top depth <len> length <len>` or `{key} both depth <len> length <len> [bottom_depth <len>]`")
        return None
    depth = _geo(conn, "cope.depth", kw["depth"], design, say)
    length = _geo(conn, "cope.length", kw["length"], design, say)
    bottom = _geo(conn, "cope.bottom_depth", kw["bottom_depth"], design, say) if "bottom_depth" in kw else None
    if "bottom_depth" in kw and bottom is None:
        return None
    return Cope(flanges, depth, length, bottom) if depth and length else None


# --- Kinds ----------------------------------------------------------------------------------

_BASIS = ("basis", p_word("lrfd", "asd"))
_LENGTHS = ("pitch", "gauge", "edge_vertical", "plate_edge", "bolt_line", "beam_edge", "top", "setback", "eccentricity",
            "beam_gauge", "support_gauge", "plate_width", "seat_length", "bearing_length", "distance", "unbraced_length",
            "stiffener_width", "stiffener_length", "weld_length", "tee_gauge", "panel_depth", "weld_return", "free_edge")
_COMMON: dict[str, Parser] = {
    "basis": p_word("lrfd", "asd"),
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
    "beam_weld": p_weld,
    "cope": p_cope,
    "rows": p_count,
    "columns": p_count,
    "deformation": p_word("considered", "not_considered"),
    "form": p_word("conventional", "extended"),
    "support_side": p_word("bolted", "welded"),
    "beam_side": p_word("bolted", "welded"),
    "location": p_word("interior", "end"),
    "force_kind": p_word("compressive", "tensile"),
    "pair": p_word("single", "double"),
    "flange_restrained": p_word("yes", "no"),
    "moment_at_force": p_word("below_yield", "at_yield"),
    "weathering": p_word("no", "yes"),
    **{name: p_length for name in _LENGTHS},
}


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
        ("distance", "pair", "flange_restrained", "unbraced_length", "moment_at_force"),
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
        here(f"a {component.kind} needs {', '.join(missing)}")
    _check_kind(component.kind, attrs, here)
    _check_references(name, component.kind, design, problems)
    if problems:
        raise ComponentError(tuple(problems))
    return Conn(name, component.kind, str(attrs["basis"]), attrs, component.span)


def _check_kind(kind: str, attrs: Mapping[str, object], say: Say) -> None:
    """The combinations a kind's lines must agree on."""
    side = attrs.get("support_side")
    if side == "bolted" and "support_gauge" not in attrs:
        say("a bolted support side names support_gauge (across the two bolt lines, or heel to bolt line on one angle)")
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
    if kind == "weld_bracket" and "weld_return" in attrs and isinstance(attrs.get("weld"), Weld) and attrs["weld"].sides != 1:
        say("a weld_return makes a C-shaped weld around a plate lapped on the support face: one fillet, `sides 1`")
    if kind == "bolt_bracket" and isinstance(attrs.get("rows"), int) and attrs["rows"] * attrs.get("columns", 1) < 2:
        say("an eccentric bolt group has at least two bolts")
    if kind == "hanger" and isinstance(attrs.get("support"), Member) and attrs["support"].face != "flange":
        say("a hanger hangs from the support's flange (the tee's bolts pass through it and it bends about the web)")
    if kind == "flange_force" and attrs.get("location") == "end" and "distance" not in attrs:
        say("a force at the member end names its distance from the end")
    if kind == "flange_force" and attrs.get("location") == "interior" and "distance" in attrs:
        say("an interior force takes no distance; a force near the end is at location end")
    if kind == "flange_force" and attrs.get("pair") == "double" and attrs.get("force_kind") == "tensile":
        say("a double (pair) force is compressive; J10.5 has no tensile pair")
    if (kind == "flange_force" and attrs.get("force_kind") == "compressive" and attrs.get("pair", "single") == "single"
            and not {"flange_restrained", "unbraced_length"} <= set(attrs)):
        say("a single compressive force names flange_restrained and unbraced_length, which web sidesway buckling (J10.4) reads")
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
