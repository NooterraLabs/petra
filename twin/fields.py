"""Typed readers for a steel component's attribute lines."""

from dataclasses import dataclass
from fractions import Fraction as F

from twin.data import (
    BOLT_GROUPS,
    ELECTRODES,
    GRADES,
    PRETENSION,
    angle_shape,
    hole,
    tee_shape,
    w_shape,
)


class FieldError(ValueError):
    pass


@dataclass(frozen=True)
class Grade:
    name: str
    fy: F
    fu: F


@dataclass(frozen=True)
class Bolts:
    group: str
    d: F
    threads_excluded: bool
    joint: str
    surface: str
    fillers: str

    @property
    def fnt(self):
        return BOLT_GROUPS[self.group][0]

    @property
    def fnv(self):
        return BOLT_GROUPS[self.group][2 if self.threads_excluded else 1]

    @property
    def pretension(self):
        table = PRETENSION.get(self.group, {})
        if self.d not in table:
            raise FieldError(f"no Table J3.1 pretension for {self.group} at d = {self.d} in.")
        return F(table[self.d])


@dataclass(frozen=True)
class Weld:
    fexx: F
    w: F
    sides: int


@dataclass(frozen=True)
class Cope:
    flanges: str
    depth: F
    length: F
    bottom_depth: F


class Lines:
    """One component's lines, read on demand. A missing required line raises FieldError."""

    def __init__(self, component):
        self.kind = component.kind
        self.name = component.name
        self._lines = component.lines

    def has(self, key):
        return key in self._lines

    def _args(self, key):
        if key not in self._lines:
            raise FieldError(f"{self.name}: missing line `{key}`")
        return self._lines[key]

    def _word(self, args, i, key):
        if i >= len(args) or args[i][0] != "ident":
            raise FieldError(f"{self.name}: `{key}` expects a word at position {i + 1}")
        return args[i][1]

    def _qty(self, args, i, key, dim):
        if i >= len(args) or args[i][0] != "qty" or args[i][1].dim != dim:
            raise FieldError(f"{self.name}: `{key}` expects a {dim} at position {i + 1}")
        return args[i][1].value

    def _options(self, args, start, key):
        out = {}
        i = start
        while i < len(args):
            word = self._word(args, i, key)
            if i + 1 >= len(args):
                raise FieldError(f"{self.name}: `{key}` option {word} has no value")
            nxt = args[i + 1]
            out[word] = nxt[1].value if nxt[0] == "qty" else nxt[1]
            i += 2
        return out

    def word(self, key, default=None):
        if key not in self._lines:
            if default is None:
                raise FieldError(f"{self.name}: missing line `{key}`")
            return default
        return self._word(self._args(key), 0, key)

    def length(self, key, default=None):
        if key not in self._lines:
            if default is None:
                raise FieldError(f"{self.name}: missing line `{key}`")
            return default
        return self._qty(self._args(key), 0, key, "length")

    def optional_length(self, key):
        return self.length(key) if key in self._lines else None

    def count(self, key, default=None):
        if key not in self._lines:
            if default is None:
                raise FieldError(f"{self.name}: missing line `{key}`")
            return default
        value = self._qty(self._args(key), 0, key, "count")
        if value.denominator != 1 or value < 1:
            raise FieldError(f"{self.name}: `{key}` must be a whole number")
        return int(value)

    def grade(self, name):
        if name not in GRADES:
            raise FieldError(f"{self.name}: unknown steel grade {name}")
        fy, fu = GRADES[name]
        return Grade(name, fy, fu)

    def member(self, key):
        """`<W shape> grade <grade>`"""
        args = self._args(key)
        shape = w_shape(self._word(args, 0, key))
        if self._word(args, 1, key) != "grade":
            raise FieldError(f"{self.name}: `{key}` expects `grade`")
        return shape, self.grade(self._word(args, 2, key))

    def support(self):
        """`<W shape> flange|web grade <grade>`; returns the shape, the face and the grade."""
        args = self._args("support")
        shape = w_shape(self._word(args, 0, "support"))
        face = self._word(args, 1, "support")
        if face not in ("flange", "web") or self._word(args, 2, "support") != "grade":
            raise FieldError(f"{self.name}: `support` expects `flange|web grade <grade>`")
        return shape, face, self.grade(self._word(args, 3, "support"))

    def plate(self, key):
        """`<grade> thickness <length>`"""
        args = self._args(key)
        grade = self.grade(self._word(args, 0, key))
        if self._word(args, 1, key) != "thickness":
            raise FieldError(f"{self.name}: `{key}` expects `thickness`")
        return grade, self._qty(args, 2, key, "length")

    def angle(self, key):
        """`<L shape> grade <grade> outstanding long|short`"""
        args = self._args(key)
        shape = angle_shape(self._word(args, 0, key))
        if self._word(args, 1, key) != "grade" or self._word(args, 3, key) != "outstanding":
            raise FieldError(f"{self.name}: `{key}` expects `<L> grade <grade> outstanding long|short`")
        outstanding = self._word(args, 4, key)
        if outstanding not in ("long", "short"):
            raise FieldError(f"{self.name}: outstanding is long or short")
        return shape, self.grade(self._word(args, 2, key)), outstanding

    def tee(self):
        args = self._args("tee")
        shape = tee_shape(self._word(args, 0, "tee"))
        if self._word(args, 1, "tee") != "grade":
            raise FieldError(f"{self.name}: `tee` expects `grade`")
        return shape, self.grade(self._word(args, 2, "tee"))

    def bolts(self):
        args = self._args("bolts")
        group = self._word(args, 0, "bolts")
        if group not in BOLT_GROUPS:
            raise FieldError(f"{self.name}: unknown bolt group {group}")
        if self._word(args, 1, "bolts") != "diameter":
            raise FieldError(f"{self.name}: `bolts` expects `diameter`")
        d = self._qty(args, 2, "bolts", "length")
        if self._word(args, 3, "bolts") != "threads":
            raise FieldError(f"{self.name}: `bolts` expects `threads included|excluded`")
        threads = self._word(args, 4, "bolts")
        if threads not in ("included", "excluded"):
            raise FieldError(f"{self.name}: threads are included or excluded")
        opts = self._options(args, 5, "bolts")
        return Bolts(
            group,
            d,
            threads == "excluded",
            opts.get("joint", "snug"),
            opts.get("surface", "class_a"),
            opts.get("fillers", "none"),
        )

    def weld(self, key):
        """`<electrode> size <length> [sides 1|2]`"""
        args = self._args(key)
        electrode = self._word(args, 0, key)
        if electrode not in ELECTRODES:
            raise FieldError(f"{self.name}: unknown electrode {electrode}")
        if self._word(args, 1, key) != "size":
            raise FieldError(f"{self.name}: `{key}` expects `size`")
        w = self._qty(args, 2, key, "length")
        opts = self._options(args, 3, key)
        sides = int(opts.get("sides", 1))
        return Weld(ELECTRODES[electrode], w, sides)

    def holes(self, d, plies):
        """Hole per ply from `holes <ply> <type> ...`; a ply not named has standard holes."""
        named = {}
        if "holes" in self._lines:
            args = self._lines["holes"]
            for i in range(0, len(args), 2):
                ply = self._word(args, i, "holes")
                named[ply] = self._word(args, i + 1, "holes")
        unknown = set(named) - set(plies)
        if unknown:
            raise FieldError(f"{self.name}: `holes` names unknown plies {sorted(unknown)}")
        return {ply: hole(d, named.get(ply, "std")) for ply in plies}

    def cope(self):
        if "cope" not in self._lines:
            return None
        args = self._lines["cope"]
        flanges = self._word(args, 0, "cope")
        opts = self._options(args, 1, "cope")
        if flanges not in ("top", "both") or "depth" not in opts or "length" not in opts:
            raise FieldError(f"{self.name}: `cope` expects `top|both depth <len> length <len>`")
        bottom = opts.get("bottom_depth", opts["depth"]) if flanges == "both" else F(0)
        return Cope(flanges, opts["depth"], opts["length"], bottom)
